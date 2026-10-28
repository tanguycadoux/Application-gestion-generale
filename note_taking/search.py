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

from collections.abc import Iterable
from dataclasses import dataclass, field

from django.db.models import QuerySet

from core.models import Project, Section, Tag
from core.sections import split_path, with_descendants
from core.tables import fold

from .models import NotePart
from .search_index import match_parts, quote, similar_terms, term_documents
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

    if project_ids:
        parts = parts.filter(project__in=project_ids)
    if section_ids:
        parts = parts.filter(section_id__in=with_descendants(set(section_ids)))
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
