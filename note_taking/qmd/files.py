"""Lecture des fichiers de note .qmd."""

from datetime import date
from pathlib import Path

from ..exceptions import InvalidNoteFileError
from .parser import ParsedNote


def validate_date_format(date_text):
    try:
        date.fromisoformat(date_text)
    except ValueError:
        raise InvalidNoteFileError(
            "Nom de fichier invalide : la date doit être au format AAAA-MM-JJ "
            "(exemple : 2025-11-24.qmd)."
        ) from None


def read_note_file(file) -> tuple[str, str]:
    """Lit un fichier de note nommé AAAA-MM-JJ.qmd : (date, contenu)."""
    note_date = Path(file.name).stem
    validate_date_format(note_date)

    try:
        raw_content = file.read().decode("utf-8-sig")
    except UnicodeDecodeError:
        raise InvalidNoteFileError("Le fichier n'est pas encodé en UTF-8.") from None

    return note_date, raw_content


def check_metadata_date(note_date: str, parsed_note: ParsedNote) -> None:
    if note_date != parsed_note.metadata.get("date"):
        raise InvalidNoteFileError(
            "La date des métadonnées ne correspond pas au nom du fichier."
        )
