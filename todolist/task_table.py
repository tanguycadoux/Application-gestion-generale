"""Filtres de la liste des tâches (#294, #178), sur les composants de `core.tables`.

Les filtres s'appliquent à des listes de `Todo` (toutes les tâches sont déjà
chargées pour construire l'arbre) : ce qui répond aux filtres reste affiché, avec
ses parents, atténués, pour garder l'arbre lisible (`tree.restrict_to`). Les quatre
filtres sont dans le panneau de la colonne « Tâche ».
"""

from core.models import Project
from core.sections import path_labels, with_descendants
from core.tables import Choice, ChoiceFilter, Filters, TextFilter, fold

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


def filter_project(tasks: list[Todo], name: str) -> list[Todo]:
    return [task for task in tasks if task.project.name == name]


def filter_path(tasks: list[Todo], section_id: str) -> list[Todo]:
    """Les tâches du niveau et de ses descendants (#298)."""
    ids = with_descendants({int(section_id)})
    return [task for task in tasks if task.section_id in ids]


def task_filters() -> Filters:
    """Les filtres de la liste, avec leurs choix à jour (projets et chemins)."""
    projects = Project.objects.filter(todos__isnull=False).distinct().order_by("name")
    paths = sorted(path_labels().items(), key=lambda item: item[1].casefold())
    return Filters(
        {
            "title": [
                ChoiceFilter("state", "État", STATES, keep_all, default=OPEN),
                TextFilter("title", "Titre", filter_title),
                ChoiceFilter(
                    "project",
                    "Projet",
                    [Choice(p.name, p.name, p) for p in projects],
                    filter_project,
                ),
                ChoiceFilter(
                    "path",
                    "Chemin",
                    [(str(pk), label) for pk, label in paths],
                    filter_path,
                ),
            ]
        }
    )
