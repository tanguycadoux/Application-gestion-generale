"""Date de complétion des tâches (#167).

Les tâches déjà terminées reçoivent leur date de dernière modification, que les
migrations précédentes n'ont pas touchée : le plus souvent le moment où elles ont
été cochées.
"""

from django.db import migrations, models
from django.db.models import F


def set_completed_at(apps, schema_editor):
    Todo = apps.get_model("todolist", "Todo")
    Todo.objects.filter(done=True).update(completed_at=F("updated_at"))


class Migration(migrations.Migration):
    dependencies = [
        ("todolist", "0012_parent_progress"),
    ]

    operations = [
        migrations.AddField(
            model_name="todo",
            name="completed_at",
            field=models.DateTimeField(
                blank=True, editable=False, null=True, verbose_name="terminée le"
            ),
        ),
        migrations.RunPython(set_completed_at, migrations.RunPython.noop),
    ]
