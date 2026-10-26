"""Supprime `Subject`, une fois les notes et les tâches passées aux sections
(#295)."""

from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0006_section"),
        ("note_taking", "0035_notepart_section"),
        ("todolist", "0018_todo_section"),
    ]

    operations = [
        migrations.DeleteModel(
            name="Subject",
        ),
    ]
