"""Choix de la tâche parente (#390).

Les tâches les plus proches d'abord, en groupes : même chemin que la tâche, même
projet, autres projets ; par échéance (sans échéance à la fin), puis par titre.
Les tâches terminées ne sont proposées que sur demande, sauf le parent actuel,
pour qu'une modification ne le perde pas. La tâche et ses descendantes, qui
feraient une boucle, ne le sont jamais.

Seul l'affichage est trié et filtré : un parent d'un autre projet, ou terminé,
reste permis (l'écart est signalé, #165).
"""

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import date

from django.db.models import Q
from django.utils.text import Truncator

from core.models import Project, Section
from core.sections import LABEL_SEPARATOR, existing_section, path_labels, split_path

from .models import Todo

# Au-delà, le titre est coupé (« … ») et le libellé complet passe en infobulle :
# un `<select>` prend la largeur de sa plus longue option.
TITLE_MAX_LENGTH = 80

SAME_PATH = "Même chemin"
SAME_PROJECT = "Même projet"
OTHER_PROJECTS = "Autres projets"


@dataclass
class ParentContext:
    """Ce qui ordonne la liste : où est la tâche (projet et chemin, tels que
    saisis dans le formulaire), et ce qu'il faut proposer."""

    project: Project | None = None
    section: Section | None = None
    # Chemin saisi qui n'existe pas encore : aucune tâche n'y est.
    unknown_path: bool = False
    show_done: bool = False
    todo: Todo | None = None
    current_parent_id: int | None = None

    @classmethod
    def from_data(cls, data: Mapping, todo: Todo | None = None) -> ParentContext:
        """D'après les valeurs d'un formulaire (envoyé, ou rechargé par htmx)."""
        project = _project(data.get("project"))
        names = split_path(data.get("section_path") or "")
        section = existing_section(project, names) if project and names else None
        return cls(
            project=project,
            section=section,
            unknown_path=bool(project and names and section is None),
            show_done=data.get("parent_show_done") == "1",
            todo=todo,
            current_parent_id=_pk(data.get("parent")),
        )


def _pk(value) -> int | None:
    if isinstance(value, Todo | Project):
        return value.pk
    try:
        return int(value)
    except TypeError, ValueError:
        return None


def _project(value) -> Project | None:
    if isinstance(value, Project):
        return value
    pk = _pk(value)
    return Project.objects.filter(pk=pk).first() if pk else None


def excluded_ids(todo: Todo | None) -> set[int]:
    """La tâche et ses descendantes : en faire le parent créerait une boucle."""
    if todo is None or todo.pk is None:
        return set()
    found, level = {todo.pk}, [todo.pk]
    while level:
        level = list(
            Todo.objects.filter(parent_id__in=level).values_list("pk", flat=True)
        )
        found.update(level)
    return found


@dataclass
class ParentChoices:
    """Choix du `<select>`, en groupes, et libellés complets des options coupées."""

    choices: list = field(default_factory=list)
    titles: dict[str, str] = field(default_factory=dict)


def parent_choices(context: ParentContext) -> ParentChoices:
    tasks = Todo.objects.select_related("project").exclude(
        pk__in=excluded_ids(context.todo)
    )
    if not context.show_done:
        kept = Q(done=False)
        if context.current_parent_id is not None:
            kept |= Q(pk=context.current_parent_id)
        tasks = tasks.filter(kept)
    paths = path_labels()

    groups: dict[str, list[tuple[str, str]]] = {
        SAME_PATH: [],
        SAME_PROJECT: [],
        OTHER_PROJECTS: [],
    }
    result = ParentChoices()
    for task in sorted(tasks, key=_order):
        group = _group(task, context)
        prefix = _prefix(task, group, paths)
        title = Truncator(task.title).chars(TITLE_MAX_LENGTH)
        groups[group].append((str(task.pk), prefix + title))
        if title != task.title:
            result.titles[str(task.pk)] = prefix + task.title

    result.choices = [("", "---------")]
    if context.project is None:
        # Sans projet choisi (nouvelle tâche), rien n'est proche : une seule liste.
        result.choices += groups[OTHER_PROJECTS]
    else:
        result.choices += [
            (label, options) for label, options in groups.items() if options
        ]
    return result


def _order(task: Todo) -> tuple[bool, date, str]:
    return (task.due_date is None, task.due_date or date.min, task.title.casefold())


def _group(task: Todo, context: ParentContext) -> str:
    if context.project is None or task.project_id != context.project.pk:
        return OTHER_PROJECTS
    section_id = context.section.pk if context.section else None
    if not context.unknown_path and task.section_id == section_id:
        return SAME_PATH
    return SAME_PROJECT


def _prefix(task: Todo, group: str, paths: dict[int, str]) -> str:
    """Ce que le groupe ne dit pas : le chemin hors du même chemin, et le projet
    hors du même projet."""
    if group == SAME_PATH:
        return ""
    # `path_labels` : « Projet › Réunion › Préparation ».
    where = paths[task.section_id] if task.section_id else task.project.name
    if group == SAME_PROJECT:
        where = where.removeprefix(task.project.name)
        where = where.removeprefix(LABEL_SEPARATOR)
    return where + LABEL_SEPARATOR if where else ""
