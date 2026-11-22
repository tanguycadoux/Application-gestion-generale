"""Le modèle `Todo` devient `Task` (#194) : la table, la table des tags et sa
colonne suivent ; les noms inverses `todos` deviennent `tasks`."""

import django.db.models.deletion
from django.db import migrations, models

import todolist.models


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0007_delete_subject"),
        ("todolist", "0019_alter_todo_section"),
    ]

    operations = [
        migrations.RenameModel(old_name="Todo", new_name="Task"),
        migrations.AlterField(
            model_name="task",
            name="project",
            field=models.ForeignKey(
                on_delete=todolist.models.protect_unless_dismissed,
                related_name="tasks",
                to="core.project",
                verbose_name="projet",
            ),
        ),
        migrations.AlterField(
            model_name="task",
            name="section",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="tasks",
                to="core.section",
                verbose_name="chemin",
            ),
        ),
        migrations.AlterField(
            model_name="task",
            name="tags",
            field=models.ManyToManyField(
                blank=True, related_name="tasks", to="core.tag", verbose_name="tags"
            ),
        ),
    ]
