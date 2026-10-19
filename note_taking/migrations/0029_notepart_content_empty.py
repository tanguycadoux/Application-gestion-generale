from django.db import migrations


def null_to_empty(apps, schema_editor):
    NotePart = apps.get_model("note_taking", "NotePart")
    NotePart.objects.filter(content__isnull=True).update(content="")


class Migration(migrations.Migration):
    """Contenu NULL → chaîne vide, avant de rendre le champ non nul (#48)."""

    dependencies = [
        ("note_taking", "0028_note_body_not_null"),
    ]

    operations = [
        migrations.RunPython(null_to_empty, migrations.RunPython.noop),
    ]
