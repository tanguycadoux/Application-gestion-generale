"""Avancement des parents calculé à partir de leurs enfants (#164).

Copie figée de la règle de todolist.models : moyenne arrondie de l'avancement des
enfants directs, en partant des tâches les plus profondes.
"""

from django.db import migrations


def depth(todo, parents: dict[int, int | None]) -> int:
    level, parent_id = 0, parents[todo]
    while parent_id is not None:
        level += 1
        parent_id = parents[parent_id]
    return level


def compute_parents_progress(apps, schema_editor):
    Todo = apps.get_model("todolist", "Todo")
    parents = dict(Todo.objects.values_list("pk", "parent_id"))
    progress = dict(Todo.objects.values_list("pk", "progress"))
    children: dict[int, list[int]] = {}
    for pk, parent_id in parents.items():
        if parent_id is not None:
            children.setdefault(parent_id, []).append(pk)

    for pk in sorted(children, key=lambda pk: depth(pk, parents), reverse=True):
        values = [progress[child] for child in children[pk]]
        progress[pk] = round(sum(values) / len(values))
        Todo.objects.filter(pk=pk).update(progress=progress[pk])


class Migration(migrations.Migration):
    dependencies = [
        ("todolist", "0011_task_model"),
    ]

    operations = [
        migrations.RunPython(compute_parents_progress, migrations.RunPython.noop),
    ]
