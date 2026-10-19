import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    """NotePart.subject et NotePart.tags pointent vers core.Subject et core.Tag (#20)."""

    dependencies = [
        ("core", "0002_subject_tag"),
        ("note_taking", "0023_copy_subjects_tags_to_core"),
    ]

    operations = [
        migrations.RemoveField(model_name="notepart", name="subject"),
        migrations.RemoveField(model_name="notepart", name="tags"),
        migrations.RenameField(
            model_name="notepart", old_name="subject_ref", new_name="subject"
        ),
        migrations.RenameField(
            model_name="notepart", old_name="tags_ref", new_name="tags"
        ),
        migrations.AlterField(
            model_name="notepart",
            name="subject",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="note_parts",
                to="core.subject",
            ),
        ),
        migrations.AlterField(
            model_name="notepart",
            name="tags",
            field=models.ManyToManyField(
                blank=True, related_name="note_parts", to="core.tag"
            ),
        ),
    ]
