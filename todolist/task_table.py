"""Filtres de la liste des tâches (#294, #178), sur les composants de `core.tables`.

Les filtres s'appliquent à des listes de `Task` (toutes les tâches sont déjà
chargées pour construire l'arbre) : ce qui répond aux filtres reste affiché, avec
ses parents, atténués, pour garder l'arbre lisible (`tree.restrict_to`). L'état,
le titre et l'arbre des projets et chemins sont dans le panneau de la colonne
« Tâche », l'absence d'échéance (#384) dans celui de la colonne « Échéance ».
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

from .models import Task

# État affiché : en cours par défaut, comme la liste d'avant. Les écartées ne sont
# pas des tâches de la liste (`Task.objects` les exclut) : elles ont leur tableau.
OPEN, DONE, ALL, DISMISSED = "open", "done", "all", "dismissed"
STATES = (
    (OPEN, "En cours"),
    (DONE, "Terminées"),
    (ALL, "Toutes les tâches"),
    (DISMISSED, "Écartées"),
)
STATE_LABELS = dict(STATES)


def keep_all(tasks: list[Task], state: str) -> list[Task]:
    """L'état ne retire aucune tâche d'un tableau : il choisit les arbres affichés."""
    return tasks


def filter_title(tasks: list[Task], text: str) -> list[Task]:
    needle = fold(text)
    return [task for task in tasks if needle in fold(task.title)]


def filter_tree(tasks: list[Task], chosen: tuple[tuple[str, ...], tuple[int, ...]]):
    """Les tâches d'un des projets cochés ou d'un des niveaux cochés, descendants
    compris (#302, #298)."""
    names, paths = chosen
    ids = with_descendants(set(paths))
    return [
        t
        for t in tasks
        if (t.project and t.project.name in names) or t.section_id in ids
    ]


# Échéance (#384) : « à fixer » est la rubrique du bloc « À traiter » de l'accueil,
# hors des tâches à revoir, dont le bilan règle l'échéance.
DUE_NONE, DUE_DECLARED, DUE_SET = "none", "declared", "set"
DUE_CHOICES = (
    (DUE_NONE, "Sans échéance, à fixer"),
    (DUE_DECLARED, "Sans échéance, c'est voulu"),
    (DUE_SET, "Avec échéance"),
)


def undated(task: Task) -> bool:
    """Sans échéance ni choix d'en rester là, et hors du bilan d'une note."""
    return (
        task.due_date is None
        and not task.no_due_date
        and task.note_state != Task.NoteState.TO_REVIEW
    )


def filter_due(tasks: list[Task], value: str) -> list[Task]:
    if value == DUE_NONE:
        return [task for task in tasks if undated(task)]
    if value == DUE_DECLARED:
        return [task for task in tasks if task.due_date is None and task.no_due_date]
    return [task for task in tasks if task.due_date is not None]


def read_state(data) -> str:
    """L'état demandé par `?state=` ; en cours si absent ou inconnu."""
    state = data.get("state", OPEN)
    return state if state in STATE_LABELS else OPEN


def counts_for(state: str) -> tuple[dict[int, int], dict[int, int]]:
    """Par niveau et par projet, les tâches de l'état affiché : ce que le filtre
    montrerait. Le compteur d'un niveau ne compte que ses propres tâches (le
    composant y ajoute les descendants)."""
    if state == DISMISSED:
        tasks = Task.all_objects.filter(note_state=Task.NoteState.DISMISSED)
    else:
        tasks = Task.objects.all()
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
            ],
            "due": [ChoiceFilter("due", "Échéance", DUE_CHOICES, filter_due)],
        }
    )
