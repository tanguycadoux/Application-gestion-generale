"""Chemins sous un projet (#287, #295) : un chemin est une suite de niveaux, chacun
une `Section` fille de la précédente.

À la saisie, « / » sépare les niveaux et « // » est un « / » littéral ; à
l'affichage, « › » les sépare. Ce que produisent les notes ne passe jamais par
ce texte : les titres donnent directement les niveaux.
"""

from collections.abc import Iterable

from .models import Project, Section
from .names import similar_key

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
    return _known_child(project, parent, name) or Section.objects.create(
        project=project, parent=parent, name=name
    )


def _known_child(project: Project, parent: Section | None, name: str) -> Section | None:
    siblings = Section.objects.filter(project=project, parent=parent)
    # Comparer en Python : le `LOWER` de SQLite ne replie que l'ASCII, pas « É ».
    for sibling in siblings:
        if sibling.name.casefold() == name.casefold():
            return sibling
    return None


def existing_section(project: Project, names: Iterable[str]) -> Section | None:
    """La section de ce chemin sous le projet si elle existe, sans rien créer
    (casse ignorée, comme `section_for`) ; None sans niveau ou si un niveau
    manque."""
    section = None
    for name in names:
        name = " ".join(name.split())
        if name:
            section = _known_child(project, section, name)
            if section is None:
                return None
    return section


def similar_siblings(section: Section, siblings: Iterable[Section]) -> list[Section]:
    """Les niveaux parmi `siblings` (même projet, même parent) dont le nom est proche
    de celui de `section` (`similar_key` : casse, accents, ponctuation, pluriel
    simple), `section` exceptée (#374)."""
    key = similar_key(section.name)
    return [
        sibling
        for sibling in siblings
        if sibling.pk != section.pk and similar_key(sibling.name) == key
    ]


def similar_warnings(known_projects: set[int], known_sections: set[int]) -> list[str]:
    """Les projets et niveaux créés depuis (absents de `known_projects` et
    `known_sections`) alors qu'un existant en est proche (#374) : un avertissement
    par nom, sans rien réécrire. Seul ce qui existait avant compte comme existant."""
    warnings = []
    projects = list(Project.objects.order_by("pk"))
    old_projects = [project for project in projects if project.pk in known_projects]
    for project in projects:
        if project.pk in known_projects:
            continue
        key = similar_key(project.name)
        if close := next((p for p in old_projects if similar_key(p.name) == key), None):
            warnings.append(
                f"Projet « {project.name} » créé : un projet proche, « {close.name} », "
                "existe déjà."
            )
    sections = list(Section.objects.select_related("project").order_by("pk"))
    for section in sections:
        if section.pk in known_sections:
            continue
        old_siblings = [
            other
            for other in sections
            if other.pk in known_sections
            and other.project_id == section.project_id
            and other.parent_id == section.parent_id
        ]
        if close_siblings := similar_siblings(section, old_siblings):
            place = LABEL_SEPARATOR.join(
                [section.project.name, *(levels(section)[:-1])]
            )
            warnings.append(
                f"Niveau « {section.name} » créé : un niveau proche, "
                f"« {close_siblings[0].name} », existe déjà au même endroit ({place})."
            )
    return warnings


def subtree(section: Section) -> list[Section]:
    """La section et ses descendants, à tous les niveaux."""
    found, level = [section], [section]
    while level:
        level = list(Section.objects.filter(parent__in=level))
        found += level
    return found


def sibling_named(section: Section, name: str) -> Section | None:
    """Le niveau de même parent et de même nom (casse ignorée), `section` exceptée."""
    for sibling in Section.objects.filter(
        project=section.project, parent=section.parent
    ).exclude(pk=section.pk):
        if sibling.name.casefold() == " ".join(name.split()).casefold():
            return sibling
    return None


def check_new_name(section: Section, raw: str) -> tuple[str, str]:
    """(nom nettoyé, erreur) pour renommer ce niveau ; l'erreur est vide si le nom
    convient. Un simple changement de casse est permis ; un nom déjà pris sous le
    même parent est refusé (la fusion est un autre sujet)."""
    name = " ".join(raw.split())
    longest = Section._meta.get_field("name").max_length or 200
    if not name:
        return name, "Écrivez le nouveau nom."
    if len(name) > longest:
        return name, f"Un niveau ne dépasse pas {longest} caractères."
    if name == section.name:
        return name, "C'est déjà son nom."
    if sibling_named(section, name):
        return name, (
            f"Un niveau « {name} » existe déjà à cet endroit : la fusion de deux "
            "niveaux n'est pas encore possible."
        )
    return name, ""


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


def path_suggestions() -> list[tuple[str, str]]:
    """Les chemins existants, tels qu'on les saisit, avec les projets qui les ont :
    [("Réunion/Préparation", "ASTERICS, ICONE")]. Une requête.

    Un chemin d'un niveau est aussi proposé : les parents existent. Le même chemin
    sous deux projets est une seule suggestion, qui nomme les deux.
    """
    sections = {
        section.pk: section for section in Section.objects.select_related("project")
    }
    projects: dict[str, set[str]] = {}
    for section in sections.values():
        names = [section.name]
        parent = section.parent_id
        while parent is not None:
            names.insert(0, sections[parent].name)
            parent = sections[parent].parent_id
        projects.setdefault(join_path(names), set()).add(section.project.name)
    return [
        (text, ", ".join(sorted(names, key=str.casefold)))
        for text, names in sorted(projects.items(), key=lambda item: item[0].casefold())
    ]


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
