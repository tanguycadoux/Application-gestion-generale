from django.db import migrations, models


class Migration(migrations.Migration):
    """Todo.tags pointe vers core.Tag ; l'ancien modèle Tag est supprimé (#20)."""

    dependencies = [
        ("core", "0002_subject_tag"),
        ("note_taking", "0023_copy_subjects_tags_to_core"),
        ("todolist", "0006_todo_tags_ref"),
    ]

    operations = [
        migrations.RemoveField(model_name="todo", name="tags"),
        migrations.RenameField(model_name="todo", old_name="tags_ref", new_name="tags"),
        migrations.AlterField(
            model_name="todo",
            name="tags",
            field=models.ManyToManyField(blank=True, related_name="todos", to="core.tag"),
        ),
        migrations.DeleteModel(name="Tag"),
    ]
