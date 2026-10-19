"""Copie les images de note_taking.NotePartImage dans images.Image (#25).

Les identifiants sont conservés : les note parts référencent les images
par `image:<pk>` dans leur contenu, qui n'a donc pas à être réécrit. Les
fichiers ne bougent pas sur le disque.
"""

from django.db import migrations


def copy_images(apps, schema_editor):
    NotePartImage = apps.get_model("note_taking", "NotePartImage")
    Image = apps.get_model("images", "Image")

    Image.objects.bulk_create(
        Image(pk=old.pk, name=old.original_path, kind="imported", file=old.file.name)
        for old in NotePartImage.objects.order_by("pk")
    )


class Migration(migrations.Migration):
    dependencies = [
        ("images", "0001_initial"),
        ("note_taking", "0030_alter_notepart_content"),
    ]

    operations = [
        migrations.RunPython(copy_images, migrations.RunPython.noop),
    ]
