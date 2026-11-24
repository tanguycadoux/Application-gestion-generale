"""Blocs des tâches dans la fiche d'un projet (#205) : leur tableau et leur frise."""

from urllib.parse import urlencode

from django.urls import reverse

from core.app_registry import ProjectScope

from . import task_table
from .gantt import rows_chart
from .models import Task
from .tree import TaskGroup, load_tasks, task_groups

# Les états de la liste, sans les écartées, qui n'ont pas d'arbre.
STATES = tuple(
    (value, label)
    for value, label in task_table.STATES
    if value != task_table.DISMISSED
)


def read_state(scope: ProjectScope) -> str:
    state = task_table.read_state(scope.params)
    return state if state in dict(STATES) else task_table.OPEN


def in_scope(task: Task, scope: ProjectScope) -> bool:
    if scope.section is None:
        return task.project_id == scope.project.pk
    return task.section_id in scope.section_ids


def groups_of(scope: ProjectScope) -> list[TaskGroup]:
    """Les arbres de l'état choisi qui ont une tâche du projet ou du niveau ; un parent
    d'un autre projet ou niveau reste, atténué, comme dans la liste filtrée."""
    tasks = load_tasks()
    matching = {task.pk for task in tasks if in_scope(task, scope)}
    done = {task_table.OPEN: False, task_table.DONE: True}.get(read_state(scope))
    return task_groups(tasks, matching=matching, done=done)


def tasks_block(scope: ProjectScope) -> dict:
    """Le tableau des tâches, dans l'état choisi (`?state=`)."""
    state = read_state(scope)
    groups = groups_of(scope)
    target: dict[str, object] = (
        {"path": scope.section.pk} if scope.section else {"project": scope.project.name}
    )
    if state != task_table.OPEN:
        target["state"] = state
    return {
        "groups": groups,
        "count": sum(1 for g in groups for row in g.rows if not row.muted),
        "state": state,
        "states": STATES,
        "list_url": f"{reverse('todolist:task_list')}?{urlencode(target)}",
    }


def timeline_block(scope: ProjectScope) -> dict | None:
    """La frise des tâches du tableau ; pas de bloc sans tâche."""
    chart = rows_chart([row for group in groups_of(scope) for row in group.rows])
    return {"chart": chart} if chart else None
