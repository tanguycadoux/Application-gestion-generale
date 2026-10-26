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
    # Gardée pour le contexte d'un filtre sans y répondre : affichée atténuée.
    muted: bool = False


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


def restrict_to_sections(
    children: dict[int | None, list[Todo]], section_ids: set[int]
) -> tuple[dict[int | None, list[Todo]], set[int]]:
    """Ne garde que les tâches de ces sections et leurs parents, pour qu'une tâche
    reste sous son parent dans l'arbre (#298). Renvoie l'arbre restreint et les
    tâches qui répondent au filtre."""
    tasks = [task for tasks in children.values() for task in tasks]
    matching = {task.pk for task in tasks if task.section_id in section_ids}
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
    return restricted, matching


def earliest_pending_due(rows: list[TaskRow]) -> date | None:
    dues = [
        row.task.due_date for row in rows if row.task.due_date and not row.task.done
    ]
    return min(dues) if dues else rows[0].task.due_date


def task_groups(section_ids: set[int] | None = None) -> list[TaskGroup]:
    """Un groupe par tâche racine, racines triées par échéance la plus proche.

    Avec `section_ids`, seules les tâches de ces sections (et leurs parents, pour
    le contexte, atténués) sont gardées.
    """
    children = children_map()
    matching = None
    if section_ids is not None:
        children, matching = restrict_to_sections(children, section_ids)
    groups = []
    for root in children.get(None, []):
        groups.append(TaskGroup(root, subtree_rows(root, children, 0, matching)))

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
