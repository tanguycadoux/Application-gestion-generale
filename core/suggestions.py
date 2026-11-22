"""Listes de suggestions de l'éditeur des notes (#90) : projets et niveaux de chemin.

Rien n'est créé ici : l'éditeur propose ce qui existe, et un nom nouveau se crée à
l'enregistrement de la note, comme aujourd'hui.
"""

import unicodedata
from collections import Counter
from collections.abc import Callable, Iterable
from dataclasses import dataclass

from .app_registry import section_usages
from .models import Project, Section
from .section_tree import usage_annotations
from .sections import path_labels, split_path

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


def elsewhere_suggestions(query: str, taken: Iterable[str]) -> list[tuple[str, str]]:
    """Les noms de niveau de tous les projets et de tous les rangs, avec où on les
    trouve : [("Bilan", "PDS1 › Autre › Bilan")], « (+2) » s'il y en a d'autres.

    Un nom n'est proposé qu'une fois, et pas s'il est déjà dans `taken` (les niveaux
    proposés à l'endroit où l'on écrit). Rien sans saisie : la liste de toute la base
    noierait celle du niveau.

    Les noms qui ne diffèrent que par la casse ou les accents sont un seul nom ; on
    propose sa graphie la plus courante (#377) : celle que portent le plus de
    niveaux, puis, à égalité, celle qui sert le plus (passages et tâches de ces
    niveaux, descendants exclus), puis l'ordre alphabétique. Le chemin montré est
    celui du niveau de cette graphie qui sert le plus (l'ordre alphabétique à
    égalité) ; « (+N) » compte les autres niveaux, toutes graphies confondues.
    """
    if not fold(query.strip()):
        return []
    usages = section_usages()
    rows = Section.objects.annotate(**usage_annotations(usages)).values_list(
        "pk", "name", *(f"usage_{index}" for index in range(len(usages)))
    )
    sections = {pk: (name, sum(counts)) for pk, name, *counts in rows}
    found: dict[str, list[Place]] = {}
    for pk, label in path_labels().items():
        name, used = sections[pk]
        found.setdefault(fold(name), []).append(Place(name, label, used))
    already = {fold(name) for name in taken}
    entries = []
    for key, places in found.items():
        if key in already:
            continue
        place = representative(places)
        more = f" (+{len(places) - 1})" if len(places) > 1 else ""
        entries.append((place.name, place.label + more))
    return rank_by_name(entries, query, lambda entry: entry[0])


@dataclass(frozen=True)
class Place:
    """Un niveau d'ailleurs : son nom, son chemin (« PDS1 › Autre › Bilan ») et ce
    qui l'utilise lui-même (passages et tâches)."""

    name: str
    label: str
    used: int


def representative(places: list[Place]) -> Place:
    """Le niveau qui représente des noms confondus : la graphie la plus portée, puis
    la plus utilisée, puis la première dans l'ordre alphabétique ; parmi ses
    niveaux, le plus utilisé, puis le premier chemin dans l'ordre alphabétique."""
    levels = Counter(place.name for place in places)
    used: Counter[str] = Counter()
    for place in places:
        used[place.name] += place.used
    name = min(levels, key=lambda name: (-levels[name], -used[name], fold(name), name))
    return min(
        (place for place in places if place.name == name),
        key=lambda place: (-place.used, fold(place.label), place.label),
    )
