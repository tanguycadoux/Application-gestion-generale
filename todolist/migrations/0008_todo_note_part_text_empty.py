from django.db import migrations


def null_to_empty(apps, schema_editor):
    Todo = apps.get_model("todolist", "Todo")
    Todo.objects.filter(note_part_text__isnull=True).update(note_part_text="")


class Migration(migrations.Migration):
    """Texte de note NULL → chaîne vide, avant de rendre le champ non nul (#48)."""

    dependencies = [
        ("todolist", "0007_todo_tags_core"),
    ]

    operations = [
        migrations.RunPython(null_to_empty, migrations.RunPython.noop),
    ]
