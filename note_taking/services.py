"""Services de note : import, mise à jour, note parts, TODO et images."""

from pathlib import Path

from django.db import transaction

from core.models import Project, Subject, Tag
from todolist.services import create_todo_from_dict

from .exceptions import (
    ImageAlreadyExistsError,
    ImageNotFoundError,
    InvalidNoteFileError,
    NoteAlreadyExistsError,
    NoteParseError,
)
from .models import Note, NotePart, NotePartImage
from .qmd.files import check_metadata_date, read_note_file, split_front_matter
from .qmd.parser import ParsedNote, parse_note
from .rendering import IMAGE_PATH_REGEX


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

    note = Note.objects.create(date=note_date, body=body)

    process_note_parts(note)
    return note


def process_note_parts(
    note: Note, parsed_note: ParsedNote | None = None
) -> list[NotePart]:
    """(Re)génère les NotePart et les todos associés à partir de note.body.

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

    for note_part in note_parts:
        create_todos_from_note_part(note_part)

    return note_parts


def create_todos_from_note_part(note_part: NotePart):
    part_tags = [tag.name for tag in note_part.tags.all()]
    subject = note_part.subject.name if note_part.subject else None

    if "TODO" in part_tags:
        tags = [tag for tag in part_tags if tag != "TODO"]
        if subject:
            tags.append(subject)

        for line in note_part.content.split("\n"):
            line = line.strip()
            line = line.strip("-")
            line = line.strip()
            if not line:
                continue

            todo_data = {
                "date": note_part.note.date,
                "project": note_part.project.name,
                "content": line,
                "tags": tags,
                "description": {
                    "subject": subject,
                    "tags": part_tags,
                },
            }
            create_todo_from_dict(todo_data)


def insert_noteparts_in_table(note: Note, parsed_note: ParsedNote) -> list[NotePart]:
    note_parts = []
    for parsed_part in parsed_note.parts:
        content = "\n".join(parsed_part.lines)
        content = replace_image_paths(content)

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
        note_parts.append(note_part)
    return note_parts


def replace_image_paths(content: str) -> str:
    def repl(match):
        path = match.group("path")
        name = Path(path).name

        try:
            image_obj = NotePartImage.objects.get(original_path=name)
        except NotePartImage.DoesNotExist:
            raise ImageNotFoundError(
                f"L'image {name} n'a pas été importée : l'importer avant la note."
            ) from None

        return match.group(0).replace(path, f"image:{image_obj.pk}")

    return IMAGE_PATH_REGEX.sub(repl, content)


def import_image(file):
    if NotePartImage.objects.filter(original_path=file.name).exists():
        raise ImageAlreadyExistsError(
            f"Une image avec ce nom de fichier existe déjà\xa0: {file.name}"
        )

    img = NotePartImage.objects.create(
        file=file,
        original_path=file.name,
    )
    return img
