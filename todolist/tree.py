"""Arbre des tâches pour le tableau de la liste et du détail (#166).

Une racine et ses descendants forment un groupe ; chaque tâche est une ligne
avec son niveau, placée sous son parent direct. Le tri (`?sort=`, #178) s'applique
aux frères à chaque niveau, sans jamais sortir une tâche de sous son parent, et aux
racines : par défaut l'échéance (sans échéance à la fin), les racines par l'échéance
la plus proche des tâches non terminées de leur arbre.
"""

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date

from core.tables import Column, Sort, Sorting, fold

from .models import Todo

# Colonnes triables du tableau. Une tâche sans valeur (échéance) reste à la fin dans
# les deux sens ; les égalités se départagent par titre puis par identifiant.
SORTING = Sorting(
    {
        "title": Column(key=lambda task: fold(task.title)),
        "progress": Column(key=lambda task: task.progress),
        "due": Column(key=lambda task: task.due_date),
    },
    default=Sort("due"),
)


@dataclass
class TaskRow:
    task: Todo
    level: int
    has_children: bool
    # Gardée pour le contexte d'un filtre sans y répondre : affichée atténuée.
    muted: bool = False


@dataclass
class TaskGroup:
    root: Todo
    rows: list[TaskRow] = field(default_factory=list)


def tie(task: Todo) -> tuple:
    return (fold(task.title), task.pk)


def load_tasks() -> list[Todo]:
    """Toutes les tâches (hors écartées), avec leur projet, en une requête."""
    return list(Todo.objects.select_related("project"))


def children_map(
    sort: Sort | None = None, tasks: list[Todo] | None = None
) -> dict[int | None, list[Todo]]:
    """Toutes les tâches, rangées par parent et triées, en une seule requête.

    Chaque tâche reçoit aussi son parent et ses enfants déjà chargés (`tree`),
    pour que ses incohérences se calculent sans requête de plus (#188). `tasks`
    évite de les relire quand l'appelant les a déjà.
    """
    sort = sort or SORTING.default
    children: dict[int | None, list[Todo]] = defaultdict(list)
    tasks_by_id = {
        task.pk: task for task in (tasks if tasks is not None else load_tasks())
    }
    for task in tasks_by_id.values():
        children[task.parent_id].append(task)
    for parent_id, siblings in children.items():
        children[parent_id] = SORTING.sort_items(siblings, sort, tie)
    for task in tasks_by_id.values():
        parent = tasks_by_id[task.parent_id] if task.parent_id else None
        task.tree = (parent, children.get(task.pk, []))
    return children


def subtree_rows(
    task: Todo,
    children: dict[int | None, list[Todo]],
    level: int,
    matching: set[int] | None = None,
) -> list[TaskRow]:
    muted = matching is not None and task.pk not in matching
    rows = [TaskRow(task, level, bool(children.get(task.pk)), muted)]
    for child in children.get(task.pk, []):
        rows += subtree_rows(child, children, level + 1, matching)
    return rows


def restrict_to(
    children: dict[int | None, list[Todo]], matching: set[int]
) -> dict[int | None, list[Todo]]:
    """Ne garde que les tâches qui répondent aux filtres et leurs parents, pour
    qu'une tâche reste sous son parent dans l'arbre (#298, #178)."""
    tasks = [task for tasks in children.values() for task in tasks]
    keep = set(matching)
    by_id = {task.pk: task for task in tasks}
    for pk in matching:
        parent = by_id[pk].parent_id
        while parent is not None and parent not in keep:
            keep.add(parent)
            parent = by_id[parent].parent_id
    restricted: dict[int | None, list[Todo]] = defaultdict(list)
    for parent_id, siblings in children.items():
        restricted[parent_id] = [task for task in siblings if task.pk in keep]
    return restricted


def earliest_pending_due(rows: list[TaskRow]) -> date | None:
    dues = [
        row.task.due_date for row in rows if row.task.due_date and not row.task.done
    ]
    return min(dues) if dues else rows[0].task.due_date


def group_key(sort: Sort):
    """La clé d'un groupe : celle de sa racine, sauf l'échéance, qui est la plus
    proche des tâches non terminées de son arbre."""
    if sort.column == "due":
        return lambda group: earliest_pending_due(group.rows)
    key = SORTING.columns[sort.column].key
    assert key is not None
    return lambda group: key(group.root)


def task_groups(
    tasks: list[Todo] | None = None,
    sort: Sort | None = None,
    matching: set[int] | None = None,
    done: bool | None = None,
) -> list[TaskGroup]:
    """Un groupe par tâche racine, triés selon `sort` (l'échéance par défaut).

    - `matching` : seules ces tâches (et leurs parents, pour le contexte,
      atténués) sont gardées ;
    - `done` : seulement les arbres dont la racine est terminée (`True`) ou non
      (`False`), tous si `None`.
    """
    sort = sort or SORTING.default
    children = children_map(sort, tasks)
    if matching is not None:
        children = restrict_to(children, matching)
    groups = [
        TaskGroup(root, subtree_rows(root, children, 0, matching))
        for root in children.get(None, [])
        if done is None or root.done == done
    ]
    return SORTING.sort_items(
        groups, sort, tie=lambda g: tie(g.root), key=group_key(sort)
    )


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
