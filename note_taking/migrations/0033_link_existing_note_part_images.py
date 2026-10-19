"""Crée les liens note part → image à partir des références existantes (#26).

Le contenu des note parts référence les images par `image:<pk>`. Une
référence vers une image inexistante est ignorée (elle s'affiche déjà
comme une image manquante).
"""

import re

from django.db import migrations

IMAGE_REF_REGEX = re.compile(r"\(image:(\d+)\)")


def link_images(apps, schema_editor):
    NotePart = apps.get_model("note_taking", "NotePart")
    NotePartImageLink = apps.get_model("note_taking", "NotePartImageLink")
    Image = apps.get_model("images", "Image")

    existing = set(Image.objects.values_list("pk", flat=True))
    links = []
    for part in NotePart.objects.order_by("pk"):
        pks = {int(pk) for pk in IMAGE_REF_REGEX.findall(part.content)}
        links += [
            NotePartImageLink(note_part_id=part.pk, image_id=pk)
            for pk in sorted(pks & existing)
        ]
    NotePartImageLink.objects.bulk_create(links)


class Migration(migrations.Migration):
    dependencies = [
        ("images", "0002_copy_note_part_images"),
        ("note_taking", "0032_note_part_images"),
    ]

    operations = [
        migrations.RunPython(link_images, migrations.RunPython.noop),
    ]
