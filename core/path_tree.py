"""L'arbre des chemins, réutilisable (#302) : recherche, tâches, fiche projet.

`path_tree` construit les nœuds ; le composant `{% path_tree %}` (core/templatetags/
ui.py) les affiche, en liens ou en cases à cocher. `core` ne connaît aucune app :
chacune fournit ses compteurs, un dictionnaire « clé d'une `Section` → nombre
d'éléments qui l'utilisent elle-même » (comme `project_usages` ou `section_usages`
dans `core/app_registry.py`). Le compteur d'un nœud inclut ses descendants, comme
filtrer sur un niveau les inclut (`core/sections.py`).

Modèle : `tag_tree` de research-paper-relationship-graph.
"""

from collections import defaultdict
from collections.abc import Collection, Mapping
from dataclasses import dataclass, field

from .models import Project, Section
from .sections import LABEL_SEPARATOR


@dataclass
class PathNode:
    """Un nœud de l'arbre : un projet (`pk` vide) ou un niveau."""

    pk: int | None
    project_id: int
    name: str
    # « Projet › Réunion › Préparation » pour un niveau, le nom pour un projet.
    label: str
    depth: int
    # Ce qui utilise ce niveau et ses descendants.
    count: int = 0
    selected: bool = False
    # Ouvert d'office : un de ses descendants est choisi.
    open: bool = False
    children: list[PathNode] = field(default_factory=list)
    # Adresse du nœud en mode lien, posée par le composant.
    href: str = ""

    @property
    def selectable(self) -> bool:
        return self.pk is not None

    @property
    def is_project(self) -> bool:
        return self.pk is None

    @property
    def has_children(self) -> bool:
        return bool(self.children)

    @property
    def key(self) -> str:
        """Identifiant HTML, stable d'une page à l'autre."""
        return (
            f"path-{self.pk}" if self.selectable else f"path-project-{self.project_id}"
        )


def path_tree(
    counts: Mapping[int, int],
    selected: Collection[int] = (),
    project: Project | None = None,
    only_counted: bool = False,
    project_counts: Mapping[int, int] | None = None,
    selected_projects: Collection[int] = (),
) -> list[PathNode]:
    """Les nœuds à plat, parents d'abord, frères triés par nom sans casse.

    - `counts` : par clé de niveau, ce qui l'utilise lui-même ; le compteur d'un
      nœud ajoute ceux de ses descendants ;
    - `selected` : clés des niveaux choisis ;
    - `project` : seulement ses niveaux, sans nœud de projet au sommet ; sinon
      chaque projet qui a des niveaux est un nœud de profondeur 0 ;
    - `only_counted` : ne garde que les niveaux utilisés ou choisis, avec leurs
      parents ;
    - `project_counts` : par identifiant de projet, ce qui l'utilise (niveaux ou
      non). Avec lui, un projet sans niveau est aussi un nœud, et son compteur ne
      se déduit plus des niveaux ;
    - `selected_projects` : identifiants des projets choisis (cases de projets).

    Une requête, deux avec `project_counts`.
    """
    sections = Section.objects.select_related("project")
    if project is not None:
        sections = sections.filter(project=project)
    chosen_projects = set(selected_projects)
    children: dict[tuple[int, int | None], list[Section]] = defaultdict(list)
    projects: dict[int, Project] = {}
    for section in sections:
        children[(section.project_id, section.parent_id)].append(section)
        projects[section.project_id] = section.project
    if project_counts is not None and project is None:
        projects.update(Project.objects.in_bulk())
    chosen = set(selected)

    def build(section: Section, labels: list[str], depth: int) -> PathNode | None:
        names = [*labels, section.name]
        node = PathNode(
            section.pk,
            section.project_id,
            section.name,
            LABEL_SEPARATOR.join(names),
            depth,
            count=counts.get(section.pk, 0),
            selected=section.pk in chosen,
        )
        for child in sorted_by_name(children[(section.project_id, section.pk)]):
            built = build(child, names, depth + 1)
            if built is not None:
                node.children.append(built)
                node.count += built.count
                node.open = node.open or built.selected or built.open
        keep = not only_counted or node.count or node.selected or node.children
        return node if keep else None

    roots: list[PathNode] = []
    if project is not None:
        for section in sorted_by_name(children[(project.pk, None)]):
            built = build(section, [project.name], 0)
            if built is not None:
                roots.append(built)
    else:
        for owner in sorted_by_name(projects.values()):
            top = PathNode(
                None,
                owner.pk,
                owner.name,
                owner.name,
                0,
                selected=owner.pk in chosen_projects,
            )
            for section in sorted_by_name(children[(owner.pk, None)]):
                built = build(section, [owner.name], 1)
                if built is not None:
                    top.children.append(built)
                    top.count += built.count
                    top.open = top.open or built.selected or built.open
            if project_counts is not None:
                top.count = project_counts.get(owner.pk, 0)
            keep = top.children or (
                project_counts is not None
                and (not only_counted or top.count or top.selected)
            )
            if keep:
                roots.append(top)

    flat: list[PathNode] = []

    def flatten(node: PathNode) -> None:
        flat.append(node)
        for child in node.children:
            flatten(child)

    for root in roots:
        flatten(root)
    return flat


def sorted_by_name(items):
    return sorted(items, key=lambda item: item.name.casefold())
