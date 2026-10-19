"""Retire le bloc d'en-tête qmd du corps des notes existantes (#24).

La date de la note fait foi : le bloc d'en-tête, qui ne contenait que la
date, sera régénéré à l'export. Par sécurité, la migration échoue si un
bloc d'en-tête contient une autre métadonnée que la date, ou une date
différente de celle de la note : rien n'est alors modifié.

Les corps vides (NULL) deviennent des chaînes vides.
"""

from django.db import migrations

DELIMITER = "---"


def split_front_matter(text):
    """Copie figée de note_taking.qmd.files.split_front_matter."""
    lines = text.split("\n")
    start = next((i for i, line in enumerate(lines) if line.strip()), None)
    if start is None or lines[start].strip() != DELIMITER:
        return {}, text
    end = next(
        (i for i in range(start + 1, len(lines)) if lines[i].strip() == DELIMITER),
        None,
    )
    if end is None:
        raise ValueError("bloc d'en-tête non fermé")
    metadata = {}
    for line in lines[start + 1 : end]:
        if line.strip():
            key, value = line.split(":", 1)
            metadata[key.strip()] = value.strip()
    body = lines[end + 1 :]
    while body and not body[0].strip():
        body.pop(0)
    return metadata, "\n".join(body)


def strip_front_matter(apps, schema_editor):
    Note = apps.get_model("note_taking", "Note")

    for note in Note.objects.order_by("date"):
        try:
            metadata, body = split_front_matter(note.body or "")
        except ValueError as e:
            raise RuntimeError(f"Note du {note.date} : {e}") from None

        unexpected = set(metadata) - {"date"}
        if unexpected:
            raise RuntimeError(
                f"Note du {note.date} : métadonnées autres que la date "
                f"({', '.join(sorted(unexpected))}), à traiter à la main."
            )
        if "date" in metadata and metadata["date"] != str(note.date):
            raise RuntimeError(
                f"Note du {note.date} : date d'en-tête différente ({metadata['date']})."
            )

        if body != note.body:
            note.body = body
            note.save(update_fields=["body"])


class Migration(migrations.Migration):
    dependencies = [
        ("note_taking", "0026_rename_note_raw_body"),
    ]

    operations = [
        migrations.RunPython(strip_front_matter, migrations.RunPython.noop),
    ]
