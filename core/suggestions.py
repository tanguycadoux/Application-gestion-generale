"""Listes de suggestions de l'éditeur des notes (#90) : projets et niveaux de chemin.

Rien n'est créé ici : l'éditeur propose ce qui existe, et un nom nouveau se crée à
l'enregistrement de la note, comme aujourd'hui.
"""

import unicodedata
from collections.abc import Callable, Iterable

from .models import Project, Section
from .sections import split_path

LIMIT = 50


def fold(text: str) -> str:
    """Le texte sans casse ni accents : « Étude » et « etude » se confondent.

    Comparé en Python : le `LOWER` de SQLite ne replie que l'ASCII, pas « É ».
    """
    decomposed = unicodedata.normalize("NFD", text.casefold())
    return "".join(c for c in decomposed if not unicodedata.combining(c))


def rank_by_name[T](
    items: Iterable[T], query: str, name: Callable[[T], str]
) -> list[T]:
    """Les éléments dont le nom contient `query` (casse et accents ignorés), au plus
    `LIMIT` : ceux qui commencent par `query` d'abord, puis l'ordre alphabétique."""
    query = fold(query.strip())
    kept = [item for item in items if query in fold(name(item))]
    kept.sort(
        key=lambda item: (not fold(name(item)).startswith(query), fold(name(item)))
    )
    return kept[:LIMIT]


def project_suggestions(query: str) -> list[Project]:
    return rank_by_name(Project.objects.all(), query, lambda project: project.name)


def section_suggestions(project_name: str, path: str, query: str) -> list[Section]:
    """Les niveaux sous `path` (« Réunion/Préparation », vide pour les premiers) du
    projet de ce nom ; rien si le projet ou un niveau du chemin n'existe pas."""
    wanted = project_name.strip().casefold()
    project = next(
        (p for p in Project.objects.all() if p.name.casefold() == wanted), None
    )
    if not wanted or project is None:
        return []
    parent = None
    for name in split_path(path):
        parent = next(
            (
                section
                for section in Section.objects.filter(project=project, parent=parent)
                if section.name.casefold() == name.casefold()
            ),
            None,
        )
        if parent is None:
            return []
    siblings = Section.objects.filter(project=project, parent=parent)
    return rank_by_name(siblings, query, lambda section: section.name)
