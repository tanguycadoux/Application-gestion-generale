"""Tâches issues des notes, avec les passages (#387, #385).

- `note_part_date` et `note_part_text` deviennent `note_date` et `note_line_text` :
  l'identité d'une tâche issue d'une note est la date de la note, le chemin et le
  texte de la ligne (#240), pas une note part. Les valeurs sont gardées.
- Le projet devient facultatif : une case du texte sans projet d'une note donne une
  tâche « à rattacher à un projet » (#385).
"""

from django.db import migrations, models

import todolist.models


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0007_delete_subject"),
        ("todolist", "0020_rename_todo_task"),
    ]

    operations = [
        migrations.RemoveConstraint(
            model_name="task",
            name="unique_note_line_when_created_from_note",
        ),
        migrations.RenameField(
            model_name="task", old_name="note_part_date", new_name="note_date"
        ),
        migrations.RenameField(
            model_name="task", old_name="note_part_text", new_name="note_line_text"
        ),
        migrations.AddConstraint(
            model_name="task",
            constraint=models.UniqueConstraint(
                condition=models.Q(("created_from_note", True)),
                fields=("created_from_note", "note_date", "note_path", "note_line_text"),
                name="unique_note_line_when_created_from_note",
            ),
        ),
        migrations.AlterField(
            model_name="task",
            name="project",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=todolist.models.protect_unless_dismissed,
                related_name="tasks",
                to="core.project",
                verbose_name="projet",
            ),
        ),
    ]
