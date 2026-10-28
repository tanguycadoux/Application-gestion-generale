"""Filtres de la liste des tâches (#294, #178), sur les composants de `core.tables`.

Les filtres s'appliquent à des listes de `Todo` (toutes les tâches sont déjà
chargées pour construire l'arbre) : ce qui répond aux filtres reste affiché, avec
ses parents, atténués, pour garder l'arbre lisible (`tree.restrict_to`). Les quatre
filtres sont dans le panneau de la colonne « Tâche ».
"""

from collections import Counter

from core.path_tree import path_tree
from core.sections import with_descendants
from core.tables import (
    ChoiceFilter,
    Filters,
    PathTreeFilter,
    TextFilter,
    fold,
)

from .models import Todo

# État affiché : en cours par défaut, comme la liste d'avant. Les écartées ne sont
# pas des tâches de la liste (`Todo.objects` les exclut) : elles ont leur tableau.
OPEN, DONE, ALL, DISMISSED = "open", "done", "all", "dismissed"
STATES = (
    (OPEN, "En cours"),
    (DONE, "Terminées"),
    (ALL, "Toutes les tâches"),
    (DISMISSED, "Écartées"),
)
STATE_LABELS = dict(STATES)


def keep_all(tasks: list[Todo], state: str) -> list[Todo]:
    """L'état ne retire aucune tâche d'un tableau : il choisit les arbres affichés."""
    return tasks


def filter_title(tasks: list[Todo], text: str) -> list[Todo]:
    needle = fold(text)
    return [task for task in tasks if needle in fold(task.title)]


def filter_tree(tasks: list[Todo], chosen: tuple[tuple[str, ...], tuple[int, ...]]):
    """Les tâches d'un des projets cochés ou d'un des niveaux cochés, descendants
    compris (#302, #298)."""
    names, paths = chosen
    ids = with_descendants(set(paths))
    return [t for t in tasks if t.project.name in names or t.section_id in ids]


def read_state(data) -> str:
    """L'état demandé par `?state=` ; en cours si absent ou inconnu."""
    state = data.get("state", OPEN)
    return state if state in STATE_LABELS else OPEN


def counts_for(state: str) -> tuple[dict[int, int], dict[int, int]]:
    """Par niveau et par projet, les tâches de l'état affiché : ce que le filtre
    montrerait. Le compteur d'un niveau ne compte que ses propres tâches (le
    composant y ajoute les descendants)."""
    if state == DISMISSED:
        tasks = Todo.all_objects.filter(note_state=Todo.NoteState.DISMISSED)
    else:
        tasks = Todo.objects.all()
        if state in (OPEN, DONE):
            tasks = tasks.filter(done=state == DONE)
    rows = tasks.values_list("project_id", "section_id")
    projects = Counter(project for project, _ in rows)
    sections = Counter(section for _, section in rows if section is not None)
    return dict(sections), dict(projects)


def task_filters(state: str = OPEN) -> Filters:
    """Les filtres de la liste, avec leurs choix à jour. L'arbre des projets et des
    chemins ne propose que ce que l'état affiché contient."""

    def tree(projects, paths):
        sections, per_project = counts_for(state)
        return path_tree(
            sections,
            paths,
            only_counted=True,
            project_counts=per_project,
            selected_projects=projects,
            project_key=lambda project: project.name,
        )

    return Filters(
        {
            "title": [
                ChoiceFilter("state", "État", STATES, keep_all, default=OPEN),
                TextFilter("title", "Titre", filter_title),
                PathTreeFilter("path", "Projets et chemins", tree, filter_tree),
            ]
        }
    )
