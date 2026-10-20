"""Avancement des parents calculé, état « terminée » validé à la main (#164).

Copie figée des règles de todolist.models :
- terminée : d'abord reprise de l'avancement (100 %), avant tout recalcul, pour
  garder la validation des parents terminés ;
- avancement d'un parent : moyenne arrondie de celui de ses enfants directs, des
  tâches les plus profondes aux racines ;
- un parent terminé dont un enfant ne l'est pas est décoché.
"""

from django.db import migrations, models


def depth(pk: int, parents: dict[int, int | None]) -> int:
    level, parent_id = 0, parents[pk]
    while parent_id is not None:
        level += 1
        parent_id = parents[parent_id]
    return level


def compute_parents(apps, schema_editor):
    Todo = apps.get_model("todolist", "Todo")
    parents = dict(Todo.objects.values_list("pk", "parent_id"))
    progress = dict(Todo.objects.values_list("pk", "progress"))
    done = {pk: value == 100 for pk, value in progress.items()}
    children: dict[int, list[int]] = {}
    for pk, parent_id in parents.items():
        if parent_id is not None:
            children.setdefault(parent_id, []).append(pk)

    for pk in sorted(children, key=lambda pk: depth(pk, parents), reverse=True):
        values = [progress[child] for child in children[pk]]
        progress[pk] = round(sum(values) / len(values))
        done[pk] = done[pk] and all(done[child] for child in children[pk])

    for pk in progress:
        Todo.objects.filter(pk=pk).update(progress=progress[pk], done=done[pk])


class Migration(migrations.Migration):
    dependencies = [
        ("todolist", "0011_task_model"),
    ]

    operations = [
        migrations.AddField(
            model_name="todo",
            name="done",
            field=models.BooleanField(default=False, verbose_name="terminée"),
        ),
        migrations.RunPython(compute_parents, migrations.RunPython.noop),
    ]
