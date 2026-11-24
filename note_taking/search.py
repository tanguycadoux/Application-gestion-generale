"""Recherche des passages (#199) : une requête analysée, appliquée à la base.

L'analyse est dans `search_query.py` (sans base) et l'index plein texte dans
`search_index.py`. Ici, les deux se rejoignent :

- les mots, phrases et préfixes passent par l'index (tous requis) ; les exclusions
  sont cherchées à passage et retirées, pour qu'`-mot` marche même seul ;
- un mot est cherché à sa forme réduite (#372, `word_forms.py`) : le singulier trouve
  le pluriel, et l'inverse ; la phrase exacte et le préfixe restent tels qu'écrits ;
- `sans:projet` et la case « Sans projet » gardent le texte sans projet, écrit avant
  le premier titre `#` (#385) ; `-sans:projet` le retire ;
- `projet:` et `chemin:` répétés se cumulent (un passage n'a qu'un projet et un
  chemin), `tag:` répété est exigé en entier (un passage a plusieurs tags) ;
- les noms se comparent sans casse ni accents (`core.tables.fold`), en Python : le
  `LOWER` de SQLite ne replie que l'ASCII ;
- `chemin:` suit les niveaux (« Réunion/Préparation ») à toute profondeur et dans tous
  les projets, et inclut les descendants (#365) ; ses noms de niveaux se comparent à
  leur forme réduite, comme les mots (#372), et `chemin:réunion*` est un préfixe
  (#368) : voir `search_paths.py` ;
- les fautes de frappe (#200) : un mot libre sans résultat ou rare est élargi aux mots
  proches de l'index (`expand_query`), les résultats exacts passant avant les élargis.
"""

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field

from django.db.models import Count, Q, QuerySet
from django.urls import reverse
from django.utils.safestring import SafeString, mark_safe

from core.dates import date_text
from core.models import Project, Section, Tag
from core.sections import with_descendants
from core.tables import fold

from .models import Note, Passage
from .qmd.parser import heading_name
from .rendering import heading_anchor, render_passage
from .search_document import GROUPS, DocPassage, Level, assemble, split_titles
from .search_index import (
    WORDS,
    WRITTEN,
    match_passages,
    quote,
    similar_terms,
    snippets,
    term_documents,
    tolerated_typos,
)
from .search_paths import section_ids_at
from .search_query import SearchQuery, Term
from .word_forms import reduce_text, written_forms

# Un mot libre est élargi s'il est dans moins de RARE passages. Au plus
# MAX_ALTERNATIVES mots proches par mot (fautes tolérées : `tolerated_typos`).
RARE = 2
MAX_ALTERNATIVES = 3


@dataclass
class Expansion:
    """Les mots proches de l'index pour certains mots libres de la requête."""

    alternatives: dict[str, list[str]] = field(default_factory=dict)

    def __bool__(self) -> bool:
        return bool(self.alternatives)


def expand_query(query: SearchQuery) -> Expansion:
    """Les mots proches des mots libres sans résultat ou rares.

    Seuls les mots simples (lettres seules) sont élargis : jamais une phrase entre
    guillemets, un préfixe, un terme exclu, une valeur d'opérateur, ni un mot avec
    chiffre ou ponctuation. Le singulier et le pluriel comptent ensemble (#372).
    """
    expansion = Expansion()
    for term in query.terms:
        if term.negated or term.kind != "word" or not term.text.isalpha():
            continue
        distance = tolerated_typos(term.text)
        if not distance or term_documents(term.text) >= RARE:
            continue
        close = [word for word, _ in similar_terms(term.text, distance)]
        if close:
            expansion.alternatives[term.text] = close[:MAX_ALTERNATIVES]
    return expansion


def search_passages(
    query: SearchQuery,
    project_ids: Iterable[int] = (),
    section_ids: Iterable[int] = (),
    expand: bool = True,
    no_project: bool = False,
) -> list[Passage] | None:
    """Les passages qui répondent à la requête et aux filtres de la page.

    Renvoie `None` quand il n'y a rien à chercher (on n'a pas encore cherché), et
    une liste, éventuellement vide, sinon. Avec du texte, le plus pertinent vient
    en premier ; sans texte, la note la plus récente, dans l'ordre de ses passages.

    `expand` (#200) élargit les mots sans résultat ou rares aux mots proches de
    l'index : ceux qui ont servi sont dans `query.expansions` (écrit, trouvé), et les
    résultats exacts passent avant les élargis.

    `no_project` : la case « Sans projet » de l'arbre (#385), réunie aux projets et
    aux niveaux cochés par « ou », comme eux.
    """
    project_ids = list(project_ids)
    section_ids = list(section_ids)
    if not (query or project_ids or section_ids or no_project):
        return None

    passages: QuerySet[Passage] = Passage.objects.select_related(
        "note", "section", "project"
    ).prefetch_related("tags")

    # Les projets et les niveaux cochés sont réunis par « ou », comme dans l'arbre
    # des tâches : un projet et le chemin d'un autre projet donnent les deux.
    chosen = Q()
    if project_ids:
        chosen |= Q(project__in=project_ids)
    if section_ids:
        chosen |= Q(section_id__in=with_descendants(set(section_ids)))
    if no_project:
        chosen |= Q(project__isnull=True)
    passages = passages.filter(chosen)
    if query.no_project is not None:
        passages = passages.filter(project__isnull=query.no_project)
    passages = filter_projects(passages, query)
    passages = filter_tags(passages, query)
    passages = filter_paths(passages, query)
    if query.date_from:
        passages = passages.filter(note__date__gte=query.date_from)
    if query.date_to:
        passages = passages.filter(note__date__lte=query.date_to)

    wanted = [term for term in query.terms if not term.negated]
    unwanted = [term for term in query.terms if term.negated]
    if unwanted:
        passages = passages.exclude(
            pk__in=match_passages(fts_expression(unwanted, " OR "))
        )

    if not wanted:
        return list(passages.order_by("-note__date", "position", "pk"))
    ordered = match_passages(fts_expression(wanted, " AND "))
    expansion = expand_query(query) if expand else Expansion()
    if expansion:
        widened = match_passages(fts_expression(wanted, " AND ", expansion))
        exact = set(ordered)
        extra = [pk for pk in widened if pk not in exact]
        if extra:
            ordered += extra
            query.expansions = [
                (written, found)
                for written, words in expansion.alternatives.items()
                for found in words
            ]
    rank = {pk: i for i, pk in enumerate(ordered)}
    return sorted(passages.filter(pk__in=rank), key=lambda passage: rank[passage.pk])


def fts_expression(
    terms: list[Term],
    joiner: str,
    expansion: Expansion | None = None,
    written: bool = False,
) -> str:
    """Requête FTS5 de ces termes : tous (`" AND "`) ou l'un d'eux (`" OR "`).

    Une phrase et un préfixe sont cherchés dans le texte tel qu'écrit (`WRITTEN`), un
    mot à sa forme réduite dans `WORDS` (#372) ; un mot élargi (#200) devient
    `words : ("écrit" OR "proche" …)`. `written` cherche aussi les mots dans le texte
    tel qu'écrit, tels que tapés et sous chacune des écritures de leur forme réduite
    (`written_forms`) : c'est la requête des extraits, qui surlignent le mot tel qu'il
    est écrit dans la note. Le mot tapé y est toujours : FTS5 le replie comme le
    texte, et il reste surligné quand ses écritures ne sont pas dans la note (« m² »,
    que `fold` change en « m2 », ou une adresse aux combinaisons trop nombreuses).
    """
    alternatives = expansion.alternatives if expansion else {}
    pieces = []
    for term in terms:
        if term.kind == "phrase":
            pieces.append(f"{WRITTEN} : {quote(term.text)}")
            continue
        if term.kind == "prefix":
            pieces.append(f"{WRITTEN} : {quote(term.text)}*")
            continue
        # Les mots proches sont des mots de l'index, déjà à leur forme réduite.
        reduced = [reduce_text(term.text), *alternatives.get(term.text, [])]
        if written:
            column = WRITTEN
            words = [
                term.text,
                *(form for word in reduced for form in written_forms(word)),
            ]
        else:
            column, words = WORDS, reduced
        options = " OR ".join(quote(word) for word in dict.fromkeys(words))
        pieces.append(f"{column} : ({options})")
    return joiner.join(pieces)


def filter_projects(
    passages: QuerySet[Passage], query: SearchQuery
) -> QuerySet[Passage]:
    if query.projects:
        passages = passages.filter(project__in=project_ids_named(query.projects))
    if query.not_projects:
        passages = passages.exclude(project__in=project_ids_named(query.not_projects))
    return passages


def filter_tags(passages: QuerySet[Passage], query: SearchQuery) -> QuerySet[Passage]:
    for name in query.tags:
        passages = passages.filter(tags__in=tag_ids_named([name]))
    if query.not_tags:
        passages = passages.exclude(tags__in=tag_ids_named(query.not_tags))
    return passages


def filter_paths(passages: QuerySet[Passage], query: SearchQuery) -> QuerySet[Passage]:
    if query.paths:
        passages = passages.filter(section_id__in=section_ids_at(query.paths))
    if query.not_paths:
        passages = passages.exclude(section_id__in=section_ids_at(query.not_paths))
    return passages


def project_ids_named(names: list[str]) -> list[int]:
    wanted = {fold(name) for name in names}
    return [p.pk for p in Project.objects.all() if fold(p.name) in wanted]


def tag_ids_named(names: list[str]) -> list[int]:
    wanted = {fold(name) for name in names}
    return [t.pk for t in Tag.objects.all() if fold(t.name) in wanted]


# Présentation des résultats (#356) : les extraits (une carte par passage), ou le
# document (les passages assemblés en Markdown, regroupés par date ou par chemin).
VIEWS = ("extraits", "document")
DEFAULT_VIEW = "extraits"
DEFAULT_GROUP = "date"

# Tri des résultats (#430).
DATE_SORTS = ("newest", "oldest")
SORTS = ("relevance", *DATE_SORTS)


def result_options(params: Mapping[str, str]) -> tuple[str, str]:
    """La vue et le regroupement demandés (`?view=`, `?group=`) ; une valeur inconnue
    est remplacée par la valeur par défaut."""
    view = params.get("view", DEFAULT_VIEW)
    group = params.get("group", DEFAULT_GROUP)
    return (
        view if view in VIEWS else DEFAULT_VIEW,
        group if group in GROUPS else DEFAULT_GROUP,
    )


def result_sort(params: Mapping[str, str], with_relevance: bool) -> str:
    """Le tri demandé (`?sort=`, #430). Par défaut, et pour une valeur inconnue ou
    impossible : la pertinence, ou les notes les plus récentes d'abord si elle ne
    s'applique pas (filtres seuls, vue « Document »)."""
    sort = params.get("sort", "")
    if with_relevance:
        return sort if sort in SORTS else "relevance"
    return sort if sort in DATE_SORTS else "newest"


def sort_passages(passages: list[Passage], sort: str) -> list[Passage]:
    """Les passages par date de leur note (#430), chaque note dans l'ordre où elle est
    écrite ; la pertinence est l'ordre de `search_passages`."""
    if sort not in DATE_SORTS:
        return passages
    sign = -1 if sort == "newest" else 1
    return sorted(
        passages,
        key=lambda p: (sign * p.note.date.toordinal(), p.position, p.pk),
    )


@dataclass
class Crumb:
    """Un niveau du chemin d'un résultat : son titre à lire, et son ancre dans la note."""

    title: str
    anchor: str | None


@dataclass
class Hit:
    """Un passage trouvé : son extrait surligné (s'il y a du texte à chercher),
    l'ancre de sa section dans la page de la note, et son chemin ascendant (#356)."""

    passage: Passage
    snippet: SafeString | None
    anchor: str | None
    crumbs: list[Crumb] = field(default_factory=list)

    @property
    def ancestors(self) -> list[Crumb]:
        """Les niveaux au-dessus du dernier, du projet vers le plus profond."""
        return self.crumbs[:-1]

    @property
    def last(self) -> Crumb | None:
        return self.crumbs[-1] if self.crumbs else None


@dataclass
class NoteResults:
    note: Note
    hits: list[Hit] = field(default_factory=list)


def group_by_note(query: SearchQuery, passages: list[Passage]) -> list[NoteResults]:
    """Les résultats par note, dans l'ordre de leur premier passage (donc la note du
    passage le plus pertinent d'abord), avec extraits et ancres (#201).

    Chaque titre du chemin mène à sa propre occurrence dans la note : l'identifiant
    enregistré avec le passage (#387), y compris pour un titre répété.
    """
    wanted = [term for term in query.terms if not term.negated]
    # Les mots élargis (#200) sont surlignés aussi : un résultat élargi a son extrait.
    alternatives: dict[str, list[str]] = {}
    for written, found in query.expansions:
        alternatives.setdefault(written, []).append(found)
    # Les extraits cherchent les mots tels qu'écrits dans la note (#372). Les
    # passages ont déjà tous les termes : `OR` garde l'extrait quand l'un d'eux n'est
    # pas trouvé tel qu'écrit (une forme réduite que la note n'écrit pas).
    expression = fts_expression(wanted, " OR ", Expansion(alternatives), written=True)
    extracts = (
        snippets(expression, [passage.pk for passage in passages]) if wanted else {}
    )
    groups: dict[int, NoteResults] = {}
    for passage in passages:
        titles = split_titles(passage.heading_path)
        anchors = passage_anchors(passage, titles)
        crumbs = [
            Crumb(heading_name(title), anchor)
            for title, anchor in zip(titles, anchors, strict=True)
        ]
        group = groups.setdefault(passage.note_id, NoteResults(passage.note))
        group.hits.append(
            Hit(
                passage,
                extracts.get(passage.pk),
                anchors[-1] if anchors else None,
                crumbs,
            )
        )
    return list(groups.values())


def passage_anchors(passage: Passage, titles: tuple[str, ...]) -> list[str | None]:
    """L'identifiant de chaque titre du chemin d'un passage dans la page de sa note.

    Ceux enregistrés à l'analyse (`anchor_path`) ; à défaut (un passage enregistré
    sans eux), celui que prend le titre seul, qui est celui de sa première
    occurrence.
    """
    stored = passage.anchor_path.split()
    if len(stored) == len(titles):
        return list(stored)
    return [heading_anchor(title) for title in titles]


# Le premier niveau du document pour le texte sans projet (#385) : aucune clé de
# projet ne vaut 0.
NO_PROJECT = Level(0, "Sans projet")


def document_html(
    passages: list[Passage], group: str, oldest_first: bool = False
) -> SafeString:
    """Les passages assemblés en un document, rendu comme une note (#356).

    Les numéros des tableaux et figures se calculent sur le texte assemblé. Dans une
    note, les passages restent dans l'ordre où ils sont écrits (#387). Les titres
    sont ceux des niveaux en base (#369) ; le lien d'un passage mène à son titre dans
    sa note, à sa propre occurrence.
    """
    levels = levels_of(passages)
    pieces = []
    for passage in sorted(
        passages, key=lambda passage: (passage.note_id, passage.position, passage.pk)
    ):
        anchors = passage_anchors(passage, split_titles(passage.heading_path))
        anchor = anchors[-1] if anchors else None
        note_url = reverse("note_taking:note_detail", args=[passage.note.date])
        pieces.append(
            DocPassage(
                date=passage.note.date,
                date_label=date_text(passage.note.date, "long"),
                note_url=note_url,
                passage_url=note_url + (f"#{anchor}" if anchor else ""),
                levels=levels[passage.pk],
                content=passage.content,
            )
        )
    return mark_safe(render_passage(assemble(pieces, group, oldest_first)))


def levels_of(passages: list[Passage]) -> dict[int, tuple[Level, ...]]:
    """Par passage, ses niveaux en base : le projet, puis sa section et ses
    ancêtres, de la racine au plus profond. Une requête pour toutes les sections.
    Le texte sans projet n'a que `NO_PROJECT`."""
    sections: dict[int, tuple[int | None, str]] = {}
    if any(passage.section_id is not None for passage in passages):
        sections = {
            pk: (parent_id, name)
            for pk, parent_id, name in Section.objects.values_list(
                "pk", "parent_id", "name"
            )
        }
    found: dict[int, tuple[Level, ...]] = {}
    for passage in passages:
        if passage.project is None:
            found[passage.pk] = (NO_PROJECT,)
            continue
        chain: list[Level] = []
        current = passage.section_id
        while current is not None:
            parent_id, name = sections[current]
            chain.insert(0, Level(current, name))
            current = parent_id
        found[passage.pk] = (Level(passage.project.pk, passage.project.name), *chain)
    return found


def facet_counts(passages: list[Passage]) -> tuple[dict[int, int], dict[int, int]]:
    """Par niveau, puis par projet, le nombre de ces passages qui l'utilisent : les
    compteurs de l'arbre des chemins pour un résultat (#380), sans requête de plus."""
    sections: dict[int, int] = {}
    projects: dict[int, int] = {}
    for passage in passages:
        if passage.section_id is not None:
            sections[passage.section_id] = sections.get(passage.section_id, 0) + 1
        if passage.project_id is not None:
            projects[passage.project_id] = projects.get(passage.project_id, 0) + 1
    return sections, projects


def no_project_count(passages: list[Passage] | None = None) -> int:
    """Le texte sans projet (#385) : parmi ces passages, ou dans toute la base. Le
    compteur de la case « Sans projet » de l'arbre des chemins."""
    if passages is None:
        return Passage.objects.filter(project__isnull=True).count()
    return sum(1 for passage in passages if passage.project_id is None)


def project_counts() -> dict[int, int]:
    """Par projet, le nombre de passages qui l'utilisent, pour les cases de projets
    de l'arbre des chemins (#360)."""
    rows = (
        Passage.objects.filter(project__isnull=False)
        .values("project")
        .annotate(total=Count("pk"))
    )
    return {row["project"]: row["total"] for row in rows}


def section_counts() -> dict[int, int]:
    """Par clé de niveau, le nombre de passages qui l'utilisent eux-mêmes, pour
    l'arbre des chemins (`core.path_tree`, qui ajoute les descendants) (#302)."""
    rows = (
        Passage.objects.filter(section__isnull=False)
        .values("section")
        .annotate(total=Count("pk"))
    )
    return {row["section"]: row["total"] for row in rows}
