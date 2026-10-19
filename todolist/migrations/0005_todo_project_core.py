import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    """Todo.project pointe vers core.Project ; l'ancien modèle est supprimé (#19)."""

    dependencies = [
        ("core", "0001_initial"),
        ("note_taking", "0020_copy_projects_to_core"),
        ("todolist", "0004_todo_core_project"),
    ]

    operations = [
        migrations.RemoveField(model_name="todo", name="project"),
        migrations.RenameField(
            model_name="todo", old_name="core_project", new_name="project"
        ),
        migrations.AlterField(
            model_name="todo",
            name="project",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="todos",
                to="core.project",
            ),
        ),
        migrations.DeleteModel(name="Project"),
    ]
