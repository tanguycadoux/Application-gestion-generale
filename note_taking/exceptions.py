"""Exceptions métier de la prise de notes.

Leurs messages sont destinés à l'utilisateur : les vues les affichent
tels quels. Toute autre exception est un bug et n'est pas attrapée.
"""


class NoteError(Exception):
    """Base des erreurs métier, attrapées et affichées par les vues."""


class InvalidNoteFileError(NoteError):
    """Fichier de note inutilisable : nom, encodage ou date incohérente."""


class NoteParseError(NoteError):
    """Contenu de note mal formé ou incohérent."""


class NoteAlreadyExistsError(NoteError):
    """Une note existe déjà pour cette date."""


class ImageNotFoundError(NoteError):
    """Image référencée dans une note mais non importée."""


class ImageAlreadyExistsError(NoteError):
    """Image déjà importée sous ce nom de fichier."""
