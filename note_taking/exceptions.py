"""Exceptions métier de la prise de notes (voir core.exceptions.AppError)."""

from core.exceptions import AppError


class NoteError(AppError):
    """Base des erreurs métier de la prise de notes."""


class InvalidNoteFileError(NoteError):
    """Fichier de note inutilisable : nom, encodage ou date incohérente."""


class NoteParseError(NoteError):
    """Contenu de note mal formé ou incohérent."""


class NoteAlreadyExistsError(NoteError):
    """Une note existe déjà pour cette date."""


class ImageNotFoundError(NoteError):
    """Image référencée dans une note mais non importée."""
