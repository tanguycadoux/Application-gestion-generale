import re
from datetime import date
from pathlib import Path

from django.db import transaction

from todolist.services import create_todo_from_dict

from .exceptions import (
    ImageAlreadyExistsError,
    ImageNotFoundError,
    InvalidNoteFileError,
    NoteAlreadyExistsError,
    NoteParseError,
)
from .models import Note, NotePart, NotePartImage, Project
from .rendering import IMAGE_PATH_REGEX


def validate_date_format(date_text):
    try:
        date.fromisoformat(date_text)
    except ValueError:
        raise InvalidNoteFileError(
            "Nom de fichier invalide : la date doit être au format AAAA-MM-JJ "
            "(exemple : 2025-11-24.qmd)."
        ) from None


def read_note_file(file) -> tuple[str, bool, str]:
    """Lit un fichier de note : (date, note de test ou non, contenu)."""
    filename = Path(file.name).stem

    is_test = filename[:4] == "TEST"
    note_date = filename[5:] if is_test else filename

    validate_date_format(note_date)

    try:
        raw_content = file.read().decode("utf-8-sig")
    except UnicodeDecodeError:
        raise InvalidNoteFileError("Le fichier n'est pas encodé en UTF-8.") from None

    return note_date, is_test, raw_content


def check_metadata_date(note_date: str, parsed_note: dict) -> None:
    if note_date != parsed_note["note metadata"].get("date"):
        raise InvalidNoteFileError(
            "La date des métadonnées ne correspond pas au nom du fichier."
        )


@transaction.atomic
def update_note_from_source_file(note: Note, file) -> Note:
    note_date, is_test, raw_content = read_note_file(file)

    parsed_note = parse_note_raw_file_as_dict(note_date, raw_content)
    check_metadata_date(note_date, parsed_note)

    if str(note.date) != note_date:
        raise InvalidNoteFileError(
            "Le fichier source ne correspond pas à la date de la note."
        )

    note.raw = raw_content
    note.is_test = is_test
    note.save()

    process_note_parts(note, parsed_note=parsed_note)
    return note


@transaction.atomic
def insert_note_in_table(file) -> Note:
    note_date, is_test, raw_content = read_note_file(file)

    parsed_note = parse_note_raw_file_as_dict(note_date, raw_content)
    check_metadata_date(note_date, parsed_note)

    if Note.objects.filter(date=note_date).exists():
        raise NoteAlreadyExistsError(f"Une note existe déjà pour le {note_date}.")

    note = Note.objects.create(date=note_date, is_test=is_test, raw=raw_content)

    process_note_parts(note, parsed_note=parsed_note)
    return note


def process_note_parts(note: Note, parsed_note: dict | None = None) -> list[NotePart]:
    """(Re)génère les NotePart et les todos associés à partir de note.raw.

    À appeler après chaque sauvegarde de note.raw (import fichier ou
    édition depuis le formulaire web), une fois `note` déjà persistée.
    """
    if parsed_note is None:
        parsed_note = parse_note_raw_file_as_dict(note.date, note.raw or "")

        parsed_date = parsed_note["note metadata"].get("date")
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
    if not isinstance(note_part.tags, list):
        raise TypeError

    if "TODO" in note_part.tags and isinstance(note_part.content, str):
        tags = note_part.tags.copy()
        if note_part.subject:
            tags.append(note_part.subject)
        tags.remove("TODO")

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
                    "subject": note_part.subject,
                    "tags": note_part.tags,
                },
            }
            create_todo_from_dict(todo_data)


def insert_noteparts_in_table(note: Note, parsed_note) -> list[NotePart]:
    note_parts = []
    for note_part_raw in parsed_note["content"]:
        content = "\n".join(note_part_raw["content"])
        content = replace_image_paths(content)

        project, _ = Project.objects.get_or_create(
            name=note_part_raw["project"],
            defaults={"description": note_part_raw["project"]},
        )

        note_part = NotePart(
            note=note,
            project=project,
            subject=note_part_raw["subject"],
            tags=note_part_raw["tags"],
            content=content,
        )

        note_part.save()
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


def parse_note_raw_file_as_dict(date, raw) -> dict:
    def parse_text_as_dict(text):
        parsed_text = text.split(":")
        if len(parsed_text) != 2:
            raise NoteParseError(
                f"La métadonnée est erronnée : format non type DICT ({text})"
            )

        parsed_key = parsed_text[0].strip()
        parsed_value = parsed_text[1].strip()

        return parsed_key, parsed_value

    json_content = {
        "file date": date,
        "note metadata": {},
        "content": [],
    }

    is_note_metadata_block = False
    is_local_metadata_block = False
    is_callout_block = False
    is_code_block = False
    is_title_line = False
    current_title_level = None
    hierarchy: dict[str, None | str | set] = {
        "project": None,
        "tags_under_project": None,
        "subject": None,
        "tags_under_subject": None,
    }
    for i in range(3, 7):
        hierarchy[f"title_{i}"] = None
        hierarchy[f"tags_under_title_{i}"] = None
    local_metadata_tags: set[str] = set()
    for i, line in enumerate(raw.split("\n")):
        line = line.strip()

        if not is_code_block:
            if line.strip() == "---":
                if i == 0:
                    is_note_metadata_block = True
                else:
                    is_note_metadata_block = False
                continue

            if line == r"::: {.metadata}":
                is_local_metadata_block = True
                continue

            if line[:18] == r"::: {.callout-note":
                is_callout_block = True
                continue

            if is_local_metadata_block and line == ":::":
                is_local_metadata_block = False
                continue

            if is_callout_block and line == ":::":
                is_callout_block = False
                continue

        if line[0:3] == "```":
            is_code_block = not (is_code_block)

        # Récupération des titres
        m = re.match(r"^(#+)\s+(.*)", line)
        if m and not (is_code_block or is_callout_block):
            is_title_line = True
            level = len(m.group(1))
            title = m.group(2).strip()
            current_title_level = level

            if level == 1:
                hierarchy["project"] = title
                hierarchy["tags_under_project"] = None
                hierarchy["subject"] = None
                hierarchy["tags_under_subject"] = None
                for j in range(3, 7):
                    hierarchy[f"title_{j}"] = None
                    hierarchy[f"tags_under_title_{j}"] = None
            elif level == 2:
                hierarchy["subject"] = title
                for j in range(3, 7):
                    hierarchy[f"title_{j}"] = None
                    hierarchy[f"tags_under_title_{j}"] = None
            elif level >= 3:
                hierarchy[f"title_{level}"] = title
                for j in range(level + 1, 7):
                    hierarchy[f"title_{j}"] = None
                    hierarchy[f"tags_under_title_{j}"] = None
        else:
            is_title_line = False
        if is_title_line:
            continue

        if is_note_metadata_block and is_local_metadata_block:
            raise NoteParseError(
                f"Erreur dans la lecture : à la fois block metadata local et global (ligne numéro {i + 1} : {line})"
            )

        elif is_note_metadata_block and line != "":
            parsed_key, parsed_value = parse_text_as_dict(line)
            json_content["note metadata"][parsed_key] = parsed_value

        elif is_local_metadata_block and line != "":
            parsed_key, parsed_value = parse_text_as_dict(line)

            if parsed_key == "tags":
                if parsed_value[0] != "[" or parsed_value[-1] != "]":
                    raise NoteParseError(
                        f"La métadonnée locale est erronnée : format non type ARRAY (ligne numéro {i + 1} : {line})"
                    )
                local_metadata_tags = set()
                parsed_tags = parsed_value.strip("[]").split(",")
                for tag in parsed_tags:
                    local_metadata_tags.add(tag.strip())

            match current_title_level:
                case 1:
                    hierarchy["tags_under_project"] = local_metadata_tags
                case 2:
                    hierarchy["tags_under_subject"] = local_metadata_tags
                case _:
                    hierarchy[f"tags_under_title_{current_title_level}"] = (
                        local_metadata_tags
                    )

        else:
            append_new = True
            project = hierarchy["project"]
            subject = hierarchy["subject"]
            tags: set[str] = set()
            if hierarchy["tags_under_project"] is not None:
                tags = tags.union(hierarchy["tags_under_project"])
            if hierarchy["tags_under_subject"] is not None:
                tags = tags.union(hierarchy["tags_under_subject"])
            for j in range(3, 7):
                title = hierarchy[f"title_{j}"]
                if isinstance(title, str):
                    tags.add(title)
                tags_under_title = hierarchy[f"tags_under_title_{j}"]
                if isinstance(tags_under_title, set):
                    tags = tags.union(tags_under_title)

            for json_line in json_content["content"]:
                json_line_tags = set(json_line["tags"])
                if (
                    project == json_line["project"]
                    and subject == json_line["subject"]
                    and tags == json_line_tags
                ):
                    append_new = False
                    json_line["content"].append(line)
                    break
            if append_new:
                json_content["content"].append(
                    {
                        "project": project,
                        "subject": subject,
                        "tags": list(tags),
                        "content": [line],
                    }
                )

    lines_to_remove = []
    for i, json_line in enumerate(json_content["content"]):
        content_as_str = "".join(json_line["content"])
        if content_as_str.strip() == "":
            lines_to_remove.append(i)
    for i in reversed(lines_to_remove):
        json_content["content"].pop(i)

    for json_line in json_content["content"]:
        while json_line["content"][0] == "":
            json_line["content"].pop(0)
        while json_line["content"][-1] == "":
            json_line["content"].pop(-1)

    return json_content


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
