"""Recherche des note parts (#199) : une requête analysée, appliquée à la base.

L'analyse est dans `search_query.py` (sans base) et l'index plein texte dans
`search_index.py`. Ici, les deux se rejoignent :

- les mots, phrases et préfixes passent par l'index (tous requis) ; les exclusions
  sont cherchées à part et retirées, pour qu'`-mot` marche même seul ;
- `projet:` et `chemin:` répétés se cumulent (une note part n'a qu'un projet et un
  chemin), `tag:` répété est exigé en entier (une note part a plusieurs tags) ;
- les noms se comparent sans casse ni accents (`core.tables.fold`), en Python : le
  `LOWER` de SQLite ne replie que l'ASCII ;
- `chemin:` suit les niveaux (« Réunion/Préparation ») et inclut les descendants ;
- les fautes de frappe (#200) : un mot libre sans résultat ou rare est élargi aux mots
  proches de l'index (`expand_query`), les résultats exacts passant avant les élargis.
"""

import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field

from django.db.models import Count, Q, QuerySet
from django.urls import reverse
from django.utils.safestring import SafeString, mark_safe

from core.models import Project, Section, Tag
from core.sections import split_path, with_descendants
from core.tables import fold
from core.templatetags.ui import date_text

from .models import Note, NotePart
from .rendering import heading_anchor, render_note_part
from .search_document import GROUPS, DocPart, assemble, split_titles
from .search_index import (
    match_parts,
    quote,
    similar_terms,
    snippets,
    term_documents,
)
from .search_query import SearchQuery, Term

# Un mot libre est élargi s'il est dans moins de RARE note parts. Au plus
# MAX_ALTERNATIVES mots proches par mot, et aucun sous MIN_LENGTH lettres.
RARE = 2
MAX_ALTERNATIVES = 3
MIN_LENGTH = 4


@dataclass
class Expansion:
    """Les mots proches de l'index pour certains mots libres de la requête."""

    alternatives: dict[str, list[str]] = field(default_factory=dict)

    def __bool__(self) -> bool:
        return bool(self.alternatives)


def max_distance(word: str) -> int:
    """Fautes tolérées : une pour 4 à 6 lettres, deux au-delà, aucune en dessous."""
    if len(word) < MIN_LENGTH:
        return 0
    return 1 if len(word) <= 6 else 2


def expand_query(query: SearchQuery) -> Expansion:
    """Les mots proches des mots libres sans résultat ou rares.

    Seuls les mots simples (lettres seules) sont élargis : jamais une phrase entre
    guillemets, un préfixe, un terme exclu, une valeur d'opérateur, ni un mot avec
    chiffre ou ponctuation.
    """
    expansion = Expansion()
    for term in query.terms:
        if term.negated or term.kind != "word" or not term.text.isalpha():
            continue
        distance = max_distance(term.text)
        if not distance or term_documents(fold(term.text)) >= RARE:
            continue
        close = [word for word, _ in similar_terms(term.text, distance)]
        if close:
            expansion.alternatives[term.text] = close[:MAX_ALTERNATIVES]
    return expansion


def search_note_parts(
    query: SearchQuery,
    project_ids: Iterable[int] = (),
    section_ids: Iterable[int] = (),
    expand: bool = True,
) -> list[NotePart] | None:
    """Les note parts qui répondent à la requête et aux filtres de la page.

    Renvoie `None` quand il n'y a rien à chercher (on n'a pas encore cherché), et
    une liste, éventuellement vide, sinon. Avec du texte, la plus pertinente vient
    en premier ; sans texte, la plus récente.

    `expand` (#200) élargit les mots sans résultat ou rares aux mots proches de
    l'index : ceux qui ont servi sont dans `query.expansions` (écrit, trouvé), et les
    résultats exacts passent avant les élargis.
    """
    project_ids = list(project_ids)
    section_ids = list(section_ids)
    if not (query or project_ids or section_ids):
        return None

    parts: QuerySet[NotePart] = NotePart.objects.select_related(
        "note", "section", "project"
    ).prefetch_related("tags")

    # Les projets et les niveaux cochés sont réunis par « ou », comme dans l'arbre
    # des tâches : un projet et le chemin d'un autre projet donnent les deux.
    chosen = Q()
    if project_ids:
        chosen |= Q(project__in=project_ids)
    if section_ids:
        chosen |= Q(section_id__in=with_descendants(set(section_ids)))
    parts = parts.filter(chosen)
    parts = filter_projects(parts, query)
    parts = filter_tags(parts, query)
    parts = filter_paths(parts, query)
    if query.date_from:
        parts = parts.filter(note__date__gte=query.date_from)
    if query.date_to:
        parts = parts.filter(note__date__lte=query.date_to)

    wanted = [term for term in query.terms if not term.negated]
    unwanted = [term for term in query.terms if term.negated]
    if unwanted:
        parts = parts.exclude(pk__in=match_parts(fts_expression(unwanted, " OR ")))

    if not wanted:
        return list(parts.order_by("-note__date", "-pk"))
    ordered = match_parts(fts_expression(wanted, " "))
    expansion = expand_query(query) if expand else Expansion()
    if expansion:
        widened = match_parts(fts_expression(wanted, " AND ", expansion))
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
    return sorted(parts.filter(pk__in=rank), key=lambda part: rank[part.pk])


def fts_expression(
    terms: list[Term], joiner: str, expansion: Expansion | None = None
) -> str:
    """Requête FTS5 de ces termes : tous (`" "`) ou l'un d'eux (`" OR "`).

    Un mot élargi devient `("écrit" OR "proche" …)`.
    """
    alternatives = expansion.alternatives if expansion else {}
    pieces = []
    for term in terms:
        piece = quote(term.text)
        if term.kind == "prefix":
            piece += "*"
        elif term.kind == "word" and term.text in alternatives:
            words = [piece, *(quote(word) for word in alternatives[term.text])]
            piece = "(" + " OR ".join(words) + ")"
        pieces.append(piece)
    return joiner.join(pieces)


def filter_projects(
    parts: QuerySet[NotePart], query: SearchQuery
) -> QuerySet[NotePart]:
    if query.projects:
        parts = parts.filter(project__in=project_ids_named(query.projects))
    if query.not_projects:
        parts = parts.exclude(project__in=project_ids_named(query.not_projects))
    return parts


def filter_tags(parts: QuerySet[NotePart], query: SearchQuery) -> QuerySet[NotePart]:
    for name in query.tags:
        parts = parts.filter(tags__in=tag_ids_named([name]))
    if query.not_tags:
        parts = parts.exclude(tags__in=tag_ids_named(query.not_tags))
    return parts


def filter_paths(parts: QuerySet[NotePart], query: SearchQuery) -> QuerySet[NotePart]:
    if query.paths:
        parts = parts.filter(section_id__in=section_ids_at(query.paths))
    if query.not_paths:
        parts = parts.exclude(section_id__in=section_ids_at(query.not_paths))
    return parts


def project_ids_named(names: list[str]) -> list[int]:
    wanted = {fold(name) for name in names}
    return [p.pk for p in Project.objects.all() if fold(p.name) in wanted]


def tag_ids_named(names: list[str]) -> list[int]:
    wanted = {fold(name) for name in names}
    return [t.pk for t in Tag.objects.all() if fold(t.name) in wanted]


def section_ids_at(paths: list[str]) -> set[int]:
    """Les niveaux dont le chemin (sous leur projet) s'écrit ainsi, et leurs descendants.

    « Réunion/Préparation » désigne le niveau « Préparation » sous « Réunion », dans
    n'importe quel projet ; `projet:` restreint à l'un d'eux.
    """
    rows = list(Section.objects.values_list("pk", "parent_id", "name"))
    parent = {pk: parent_id for pk, parent_id, _ in rows}
    name = {pk: fold(label) for pk, _, label in rows}

    def chain(pk: int) -> tuple[str, ...]:
        names: list[str] = []
        current: int | None = pk
        while current is not None:
            names.append(name[current])
            current = parent[current]
        return tuple(reversed(names))

    wanted = {tuple(fold(level) for level in split_path(path)) for path in paths}
    wanted.discard(())
    return with_descendants({pk for pk, _, _ in rows if chain(pk) in wanted})


# Présentation des résultats (#356) : les extraits (une carte par note part), ou le
# document (les note parts assemblées en Markdown, regroupées par date ou par chemin).
VIEWS = ("extraits", "document")
DEFAULT_VIEW = "extraits"
DEFAULT_GROUP = "date"
# `{#id}` ou `{.classe}` en fin de titre : une écriture, pas un texte à lire.
TITLE_ATTRIBUTES_REGEX = re.compile(r"\s*\{[^}]*\}\s*$")


def result_options(params: Mapping[str, str]) -> tuple[str, str]:
    """La vue et le regroupement demandés (`?view=`, `?group=`) ; une valeur inconnue
    est remplacée par la valeur par défaut."""
    view = params.get("view", DEFAULT_VIEW)
    group = params.get("group", DEFAULT_GROUP)
    return (
        view if view in VIEWS else DEFAULT_VIEW,
        group if group in GROUPS else DEFAULT_GROUP,
    )


@dataclass
class Crumb:
    """Un niveau du chemin d'un résultat : son titre à lire, et son ancre dans la note."""

    title: str
    anchor: str | None


@dataclass
class Hit:
    """Une note part trouvée : son extrait surligné (s'il y a du texte à chercher),
    l'ancre de sa section dans la page de la note, et son chemin ascendant (#356)."""

    part: NotePart
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


def group_by_note(query: SearchQuery, parts: list[NotePart]) -> list[NoteResults]:
    """Les résultats par note, dans l'ordre de leur première note part (donc la note de
    la note part la plus pertinente d'abord), avec extraits et ancres (#201)."""
    wanted = [term for term in query.terms if not term.negated]
    # Les mots élargis (#200) sont surlignés aussi : un résultat élargi a son extrait.
    alternatives: dict[str, list[str]] = {}
    for written, found in query.expansions:
        alternatives.setdefault(written, []).append(found)
    expression = (
        fts_expression(wanted, " AND ", Expansion(alternatives))
        if alternatives
        else fts_expression(wanted, " ")
    )
    extracts = snippets(expression, [part.pk for part in parts]) if wanted else {}
    anchors: dict[str, str | None] = {}
    groups: dict[int, NoteResults] = {}
    for part in parts:
        crumbs = []
        for title in split_titles(part.heading_path):
            if title not in anchors:
                anchors[title] = heading_anchor(title)
            crumbs.append(Crumb(TITLE_ATTRIBUTES_REGEX.sub("", title), anchors[title]))
        anchor = crumbs[-1].anchor if crumbs else None
        group = groups.setdefault(part.note_id, NoteResults(part.note))
        group.hits.append(Hit(part, extracts.get(part.pk), anchor, crumbs))
    return list(groups.values())


def document_html(parts: list[NotePart], group: str) -> SafeString:
    """Les note parts assemblées en un document, rendu comme une note (#356).

    Les numéros des tableaux et figures se calculent sur le texte assemblé. Dans une
    note, les note parts restent dans l'ordre où elles sont écrites.
    """
    anchors: dict[str, str | None] = {}
    pieces = []
    for part in sorted(parts, key=lambda part: part.pk):
        titles = split_titles(part.heading_path)
        last = titles[-1] if titles else ""
        if last not in anchors:
            anchors[last] = heading_anchor(last)
        note_url = reverse("note_taking:note_detail", args=[part.note.date])
        pieces.append(
            DocPart(
                date=part.note.date,
                date_label=date_text(part.note.date, "long"),
                note_url=note_url,
                part_url=note_url + (f"#{anchors[last]}" if anchors[last] else ""),
                titles=titles,
                content=part.content,
                project=part.project.name,
            )
        )
    return mark_safe(render_note_part(assemble(pieces, group)))


def project_counts() -> dict[int, int]:
    """Par projet, le nombre de note parts qui l'utilisent, pour les cases de projets
    de l'arbre des chemins (#360)."""
    rows = NotePart.objects.values("project").annotate(total=Count("pk"))
    return {row["project"]: row["total"] for row in rows}


def section_counts() -> dict[int, int]:
    """Par clé de niveau, le nombre de note parts qui l'utilisent elles-mêmes, pour
    l'arbre des chemins (`core.path_tree`, qui ajoute les descendants) (#302)."""
    rows = (
        NotePart.objects.filter(section__isnull=False)
        .values("section")
        .annotate(total=Count("pk"))
    )
    return {row["section"]: row["total"] for row in rows}
