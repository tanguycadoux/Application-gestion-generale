"""Services de note : import, mise à jour, note parts et images."""

from datetime import date
from pathlib import Path

from django.db import transaction

from core.models import Project, Subject, Tag
from images.models import Image

from .exceptions import (
    ImageNotFoundError,
    InvalidNoteFileError,
    NoteAlreadyExistsError,
    NoteParseError,
)
from .models import Note, NotePart
from .qmd.files import check_metadata_date, read_note_file, split_front_matter
from .qmd.parser import ParsedNote, parse_note
from .rendering import IMAGE_PATH_REGEX
from .signals import note_parts_processed


@transaction.atomic
def update_note_from_source_file(note: Note, file) -> Note:
    note_date, content = read_note_file(file)
    metadata, body = split_front_matter(content)
    check_metadata_date(note_date, metadata)

    if str(note.date) != note_date:
        raise InvalidNoteFileError(
            "Le fichier source ne correspond pas à la date de la note."
        )

    note.body = body
    note.save()

    process_note_parts(note)
    return note


@transaction.atomic
def insert_note_in_table(file) -> Note:
    note_date, content = read_note_file(file)
    metadata, body = split_front_matter(content)
    check_metadata_date(note_date, metadata)

    if Note.objects.filter(date=note_date).exists():
        raise NoteAlreadyExistsError(f"Une note existe déjà pour le {note_date}.")

    note = Note.objects.create(date=date.fromisoformat(note_date), body=body)

    process_note_parts(note)
    return note


def process_note_parts(
    note: Note, parsed_note: ParsedNote | None = None
) -> list[NotePart]:
    """(Re)génère les NotePart à partir de note.body, puis émet note_parts_processed.

    À appeler après chaque sauvegarde de note.body (import fichier ou
    édition depuis le formulaire web), une fois `note` déjà persistée.
    """
    if parsed_note is None:
        parsed_note = parse_note(str(note.date), note.body)

        parsed_date = parsed_note.metadata.get("date")
        if parsed_date and str(note.date) != parsed_date:
            raise NoteParseError(
                "La date dans les métadonnées du contenu ne correspond pas "
                "à la date de la note."
            )

    note.parts.all().delete()
    note_parts = insert_noteparts_in_table(note, parsed_note)

    note_parts_processed.send(sender=Note, note=note, note_parts=note_parts)

    return note_parts


def insert_noteparts_in_table(note: Note, parsed_note: ParsedNote) -> list[NotePart]:
    note_parts = []
    for parsed_part in parsed_note.parts:
        content = "\n".join(parsed_part.lines)
        content, images = replace_image_paths(content)

        project, _ = Project.objects.get_or_create(name=parsed_part.project)

        subject = (
            Subject.objects.get_or_create(name=parsed_part.subject)[0]
            if parsed_part.subject
            else None
        )

        note_part = NotePart.objects.create(
            note=note, project=project, subject=subject, content=content
        )
        note_part.tags.set(
            [Tag.objects.get_or_create(name=name)[0] for name in parsed_part.tags]
        )
        note_part.images.set(images)
        note_parts.append(note_part)
    return note_parts


def replace_image_paths(content: str) -> tuple[str, list[Image]]:
    """Remplace les chemins d'images par `image:<pk>`.

    Renvoie le contenu modifié et les images référencées, sans doublon.
    """
    images: dict[int, Image] = {}

    def repl(match):
        path = match.group("path")
        name = Path(path).name

        try:
            image_obj = Image.objects.get(name=name)
        except Image.DoesNotExist:
            raise ImageNotFoundError(
                f"L'image {name} n'a pas été importée : l'importer avant la note."
            ) from None

        images[image_obj.pk] = image_obj
        return match.group(0).replace(path, f"image:{image_obj.pk}")

    return IMAGE_PATH_REGEX.sub(repl, content), list(images.values())
