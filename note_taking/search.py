"""Recherche des note parts (#199) : une requête analysée, appliquée à la base.

L'analyse est dans `search_query.py` (sans base) et l'index plein texte dans
`search_index.py`. Ici, les deux se rejoignent :

- les mots, phrases et préfixes passent par l'index (tous requis) ; les exclusions
  sont cherchées à part et retirées, pour qu'`-mot` marche même seul ;
- `projet:` et `chemin:` répétés se cumulent (une note part n'a qu'un projet et un
  chemin), `tag:` répété est exigé en entier (une note part a plusieurs tags) ;
- les noms se comparent sans casse ni accents (`core.tables.fold`), en Python : le
  `LOWER` de SQLite ne replie que l'ASCII ;
- `chemin:` suit les niveaux (« Réunion/Préparation ») et inclut les descendants.
"""

from collections.abc import Iterable
from dataclasses import dataclass, field

from django.db.models import QuerySet
from django.utils.safestring import SafeString

from core.models import Project, Section, Tag
from core.sections import split_path, with_descendants
from core.tables import fold

from .models import Note, NotePart
from .qmd.parser import HEADING_SEPARATOR
from .rendering import heading_anchor
from .search_index import match_parts, quote, snippets
from .search_query import SearchQuery, Term


def search_note_parts(
    query: SearchQuery,
    project_ids: Iterable[int] = (),
    section_ids: Iterable[int] = (),
) -> list[NotePart] | None:
    """Les note parts qui répondent à la requête et aux filtres de la page.

    Renvoie `None` quand il n'y a rien à chercher (on n'a pas encore cherché), et
    une liste, éventuellement vide, sinon. Avec du texte, la plus pertinente vient
    en premier ; sans texte, la plus récente.
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
    rank = {pk: i for i, pk in enumerate(match_parts(fts_expression(wanted, " ")))}
    return sorted(parts.filter(pk__in=rank), key=lambda part: rank[part.pk])


def fts_expression(terms: list[Term], joiner: str) -> str:
    """Requête FTS5 de ces termes : tous (`" "`) ou l'un d'eux (`" OR "`)."""
    pieces = []
    for term in terms:
        piece = quote(term.text)
        pieces.append(piece + "*" if term.kind == "prefix" else piece)
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


@dataclass
class Hit:
    """Une note part trouvée : son extrait surligné (s'il y a du texte à chercher)
    et l'ancre de sa section dans la page de la note."""

    part: NotePart
    snippet: SafeString | None
    anchor: str | None


@dataclass
class NoteResults:
    note: Note
    hits: list[Hit] = field(default_factory=list)


def group_by_note(query: SearchQuery, parts: list[NotePart]) -> list[NoteResults]:
    """Les résultats par note, dans l'ordre de leur première note part (donc la note de
    la note part la plus pertinente d'abord), avec extraits et ancres (#201)."""
    wanted = [term for term in query.terms if not term.negated]
    extracts = (
        snippets(fts_expression(wanted, " "), [part.pk for part in parts])
        if wanted
        else {}
    )
    anchors: dict[str, str | None] = {}
    groups: dict[int, NoteResults] = {}
    for part in parts:
        title = part.heading_path.split(HEADING_SEPARATOR)[-1]
        if title not in anchors:
            anchors[title] = heading_anchor(title)
        group = groups.setdefault(part.note_id, NoteResults(part.note))
        group.hits.append(Hit(part, extracts.get(part.pk), anchors[title]))
    return list(groups.values())
