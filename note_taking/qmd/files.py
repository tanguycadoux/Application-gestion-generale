"""Lecture des fichiers de note .qmd et de leur bloc d'en-tête."""

from datetime import date
from pathlib import Path

from ..exceptions import InvalidNoteFileError, NoteParseError
from .parser import FRONT_MATTER_DELIMITER, parse_key_value


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
        content = file.read().decode("utf-8-sig")
    except UnicodeDecodeError:
        raise InvalidNoteFileError("Le fichier n'est pas encodé en UTF-8.") from None

    return note_date, content


def split_front_matter(text: str) -> tuple[dict[str, str], str]:
    """Sépare le bloc d'en-tête qmd du corps de la note.

    Le bloc d'en-tête doit être la première ligne non vide. Renvoie
    (métadonnées, corps), le corps sans les lignes vides qui suivent le bloc.
    Sans bloc d'en-tête, les métadonnées sont vides et le texte est inchangé.
    """
    lines = text.split("\n")
    start = next((i for i, line in enumerate(lines) if line.strip()), None)
    if start is None or lines[start].strip() != FRONT_MATTER_DELIMITER:
        return {}, text

    end = next(
        (
            i
            for i in range(start + 1, len(lines))
            if lines[i].strip() == FRONT_MATTER_DELIMITER
        ),
        None,
    )
    if end is None:
        raise NoteParseError("Le bloc d'en-tête n'est pas fermé (ligne --- manquante).")

    metadata = dict(
        parse_key_value(lines[i].strip(), i + 1)
        for i in range(start + 1, end)
        if lines[i].strip()
    )
    body = lines[end + 1 :]
    while body and not body[0].strip():
        body.pop(0)
    return metadata, "\n".join(body)


def check_metadata_date(note_date: str, metadata: dict[str, str]) -> None:
    header_date = metadata.get("date")
    if header_date is None:
        raise InvalidNoteFileError(
            "Le bloc d'en-tête doit indiquer la date de la note, celle du nom "
            f"du fichier : « date: {note_date} »."
        )
    if header_date != note_date:
        raise InvalidNoteFileError(
            f"La date du bloc d'en-tête ({header_date}) ne correspond pas "
            f"au nom du fichier ({note_date}.qmd)."
        )
