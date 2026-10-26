"""Arbre des tâches pour le tableau de la liste et du détail (#166).

Une racine et ses descendants forment un groupe ; chaque tâche est une ligne
avec son niveau, placée sous son parent direct. Les frères sont triés par
échéance (sans échéance à la fin), les racines par l'échéance la plus proche
des tâches non terminées de leur arbre.
"""

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date

from .models import Todo


@dataclass
class TaskRow:
    task: Todo
    level: int
    has_children: bool


@dataclass
class TaskGroup:
    root: Todo
    rows: list[TaskRow] = field(default_factory=list)


def due_key(task: Todo) -> tuple:
    return (task.due_date is None, task.due_date or date.max, task.title.lower())


def children_map() -> dict[int | None, list[Todo]]:
    """Toutes les tâches, rangées par parent, en une seule requête.

    Chaque tâche reçoit aussi son parent et ses enfants déjà chargés (`tree`),
    pour que ses incohérences se calculent sans requête de plus (#188).
    """
    children: dict[int | None, list[Todo]] = defaultdict(list)
    tasks_by_id = {task.pk: task for task in Todo.objects.select_related("project")}
    for task in tasks_by_id.values():
        children[task.parent_id].append(task)
    for tasks in children.values():
        tasks.sort(key=due_key)
    for task in tasks_by_id.values():
        parent = tasks_by_id[task.parent_id] if task.parent_id else None
        task.tree = (parent, children.get(task.pk, []))
    return children


def subtree_rows(
    task: Todo, children: dict[int | None, list[Todo]], level: int
) -> list[TaskRow]:
    rows = [TaskRow(task, level, bool(children.get(task.pk)))]
    for child in children.get(task.pk, []):
        rows += subtree_rows(child, children, level + 1)
    return rows


def earliest_pending_due(rows: list[TaskRow]) -> date | None:
    dues = [
        row.task.due_date for row in rows if row.task.due_date and not row.task.done
    ]
    return min(dues) if dues else rows[0].task.due_date


def task_groups() -> list[TaskGroup]:
    """Un groupe par tâche racine, racines triées par échéance la plus proche."""
    children = children_map()
    groups = []
    for root in children.get(None, []):
        groups.append(TaskGroup(root, subtree_rows(root, children, 0)))

    def group_key(group: TaskGroup) -> tuple:
        due = earliest_pending_due(group.rows)
        return (due is None, due or date.max, group.root.title.lower())

    return sorted(groups, key=group_key)


def task_rows(ids: list[int]) -> dict[int, TaskRow]:
    """Lignes de ces tâches, au niveau qu'elles ont dans la liste (racine = 0)."""
    children = children_map()
    rows = {}
    for tasks in children.values():
        for task in tasks:
            if task.pk in ids:
                level, (parent, _) = 0, task.tree or (None, [])
                while parent is not None:
                    level += 1
                    parent = parent.tree[0] if parent.tree else None
                rows[task.pk] = TaskRow(task, level, bool(children.get(task.pk)))
    return rows


def descendant_rows(task: Todo) -> list[TaskRow]:
    """Lignes des descendants d'une tâche, ses enfants au niveau 0 (détail).

    La tâche reçoit son parent et ses enfants déjà chargés, comme dans l'arbre.
    """
    children = children_map()
    loaded = {child.pk: child for tasks in children.values() for child in tasks}
    task.tree = (
        loaded[task.parent_id] if task.parent_id else None,
        children.get(task.pk, []),
    )
    rows = []
    for child in children.get(task.pk, []):
        rows += subtree_rows(child, children, 0)
    return rows
