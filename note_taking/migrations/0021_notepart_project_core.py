import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    """NotePart.project pointe vers core.Project ; l'ancien modèle est supprimé (#19)."""

    dependencies = [
        ("core", "0001_initial"),
        ("note_taking", "0020_copy_projects_to_core"),
    ]

    operations = [
        migrations.RemoveField(model_name="notepart", name="project"),
        migrations.RenameField(
            model_name="notepart", old_name="core_project", new_name="project"
        ),
        migrations.AlterField(
            model_name="notepart",
            name="project",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                related_name="note_parts",
                to="core.project",
            ),
        ),
        migrations.DeleteModel(name="Project"),
    ]
