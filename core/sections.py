"""Chemins sous un projet (#287, #295) : un chemin est une suite de niveaux, chacun
une `Section` fille de la précédente.

À la saisie, « / » sépare les niveaux et « // » est un « / » littéral ; à
l'affichage, « › » les sépare. Ce que produisent les notes ne passe jamais par
ce texte : les titres donnent directement les niveaux.
"""

from collections.abc import Iterable

from .models import Project, Section

INPUT_SEPARATOR = "/"
LABEL_SEPARATOR = " › "


def split_path(raw: str) -> list[str]:
    """Niveaux d'un chemin saisi : « Réunion / Préparation » donne deux niveaux,
    « RT17//A » un seul, « RT17/A ». Espaces réduits, niveaux vides ignorés."""
    levels, current, index = [], "", 0
    while index < len(raw):
        char = raw[index]
        if char == INPUT_SEPARATOR and raw[index + 1 : index + 2] == INPUT_SEPARATOR:
            current += INPUT_SEPARATOR
            index += 2
            continue
        if char == INPUT_SEPARATOR:
            levels.append(current)
            current = ""
        else:
            current += char
        index += 1
    levels.append(current)
    cleaned = (" ".join(level.split()) for level in levels)
    return [level for level in cleaned if level]


def join_path(levels: Iterable[str]) -> str:
    """Texte à saisir pour ce chemin, que `split_path` relit à l'identique."""
    return INPUT_SEPARATOR.join(
        level.replace(INPUT_SEPARATOR, INPUT_SEPARATOR * 2) for level in levels
    )


def ancestors_and_self(section: Section) -> list[Section]:
    """De la racine du chemin jusqu'à la section."""
    chain = [section]
    while (parent := chain[0].parent) is not None:
        chain.insert(0, parent)
    return chain


def levels(section: Section) -> list[str]:
    return [level.name for level in ancestors_and_self(section)]


def label(section: Section) -> str:
    """« Réunion › Préparation »."""
    return LABEL_SEPARATOR.join(levels(section))


def section_for(project: Project, names: Iterable[str]) -> Section | None:
    """La section de ce chemin sous le projet, créée si besoin ; None sans niveau.

    Un niveau connu, quelle que soit sa casse, est repris tel qu'il a été écrit la
    première fois : « réunion » retrouve « Réunion ».
    """
    section = None
    for name in names:
        name = " ".join(name.split())
        if name:
            section = _child(project, section, name)
    return section


def _child(project: Project, parent: Section | None, name: str) -> Section:
    siblings = Section.objects.filter(project=project, parent=parent)
    # Comparer en Python : le `LOWER` de SQLite ne replie que l'ASCII, pas « É ».
    for sibling in siblings:
        if sibling.name.casefold() == name.casefold():
            return sibling
    return Section.objects.create(project=project, parent=parent, name=name)


def subtree(section: Section) -> list[Section]:
    """La section et ses descendants, à tous les niveaux."""
    found, level = [section], [section]
    while level:
        level = list(Section.objects.filter(parent__in=level))
        found += level
    return found


def parent_map() -> dict[int, int | None]:
    """Le parent de chaque section : une requête pour tout l'arbre."""
    return dict(Section.objects.values_list("pk", "parent_id"))


def with_ancestors(pks: Iterable[int]) -> set[int]:
    """Les sections données et leurs ancêtres : les parents implicites d'un chemin."""
    parents = parent_map()
    found: set[int] = set()
    for pk in pks:
        current: int | None = pk
        while current is not None and current not in found:
            found.add(current)
            current = parents.get(current)
    return found


def with_descendants(pks: Iterable[int]) -> set[int]:
    """Les sections données et leurs descendants : filtrer sur un niveau les inclut."""
    children: dict[int, list[int]] = {}
    for pk, parent in parent_map().items():
        if parent is not None:
            children.setdefault(parent, []).append(pk)
    found: set[int] = set()
    pending = list(pks)
    while pending:
        pk = pending.pop()
        if pk not in found:
            found.add(pk)
            pending.extend(children.get(pk, []))
    return found


def path_labels() -> dict[int, str]:
    """« Projet › Réunion › Préparation » pour chaque section, en deux requêtes."""
    sections = {
        section.pk: section for section in Section.objects.select_related("project")
    }
    labels = {}
    for pk, section in sections.items():
        names = [section.name]
        parent = section.parent_id
        while parent is not None:
            names.insert(0, sections[parent].name)
            parent = sections[parent].parent_id
        labels[pk] = LABEL_SEPARATOR.join([section.project.name, *names])
    return labels


def forget_unused_sections() -> int:
    """Supprime les sections que rien n'utilise, descendants compris ; renvoie le
    nombre supprimé. Un niveau reste tant qu'un de ses descendants sert.

    Ce qui utilise une section, ce sont les clés étrangères qui y mènent : core ne
    connaît pas les apps, il les lit sur le modèle.
    """
    used: set[int] = set()
    for relation in Section._meta.related_objects:
        if relation.related_model is Section or not relation.one_to_many:
            continue
        used.update(
            relation.related_model._base_manager.exclude(
                **{relation.field.name: None}
            ).values_list(relation.field.attname, flat=True)
        )
    parents = dict(Section.objects.values_list("pk", "parent_id"))
    kept: set[int] = set()
    for used_pk in used:
        pk: int | None = used_pk
        while pk is not None and pk not in kept:
            kept.add(pk)
            pk = parents.get(pk)
    unused = [pk for pk in parents if pk not in kept]
    if unused:
        Section.objects.filter(pk__in=unused).delete()
    return len(unused)
