from django.db import migrations


class Migration(migrations.Migration):
    """Note.raw devient Note.body : le corps de la note, sans bloc d'en-tête (#24)."""

    dependencies = [
        ("note_taking", "0025_remove_note_is_test"),
    ]

    operations = [
        migrations.RenameField(model_name="note", old_name="raw", new_name="body"),
    ]
