"""Modèle des tâches (#163) : avancement, sujet, projet obligatoire.

Migration irréversible : revenir en arrière perdrait l'avancement partiel, le
sujet et les descriptions vidées.
"""

import ast

import django.core.validators
import django.db.models.deletion
from django.db import migrations, models


def migrate_tasks(apps, schema_editor):
    """Reprend les données ; échoue sans rien modifier si elles ne sont pas dans
    l'état attendu (la migration tourne dans une transaction)."""
    Todo = apps.get_model("todolist", "Todo")
    Subject = apps.get_model("core", "Subject")

    if Todo.objects.filter(project__isnull=True).exists():
        raise RuntimeError("Des tâches n'ont pas de projet : à corriger avant.")

    for todo in Todo.objects.all():
        todo.progress = 100 if todo.completed else 0

        if todo.created_from_note:
            # Description écrite par l'ancien import : {"subject": …, "tags": […]}.
            try:
                origin = ast.literal_eval(todo.description)
            except (ValueError, SyntaxError) as error:
                raise RuntimeError(
                    f"Description illisible pour la tâche {todo.pk} : "
                    f"{todo.description!r}"
                ) from error
            if not isinstance(origin, dict) or "subject" not in origin:
                raise RuntimeError(f"Description inattendue pour la tâche {todo.pk}.")

            subject_name = origin["subject"]
            if subject_name:
                todo.subject = Subject.objects.get(name=subject_name)
                # L'ancien import ajoutait le sujet aux tags de la tâche.
                if subject_name not in origin.get("tags", []):
                    todo.tags.remove(*todo.tags.filter(name=subject_name))
            todo.description = ""

        todo.save(update_fields=["progress", "subject", "description"])


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0004_project_verbose_names"),
        ("todolist", "0010_verbose_names_fr"),
    ]

    operations = [
        migrations.AddField(
            model_name="todo",
            name="progress",
            field=models.PositiveSmallIntegerField(
                default=0,
                validators=[django.core.validators.MaxValueValidator(100)],
                verbose_name="avancement (%)",
            ),
        ),
        migrations.AddField(
            model_name="todo",
            name="subject",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="todos",
                to="core.subject",
                verbose_name="sujet",
            ),
        ),
        migrations.RunPython(migrate_tasks),
        migrations.RemoveField(
            model_name="todo",
            name="completed",
        ),
        migrations.AlterField(
            model_name="todo",
            name="project",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                related_name="todos",
                to="core.project",
                verbose_name="projet",
            ),
        ),
    ]
