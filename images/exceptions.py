"""Exceptions métier des images."""

from core.exceptions import AppError


class ImageError(AppError):
    """Base des erreurs métier des images."""


class ImageAlreadyExistsError(ImageError):
    """Image déjà importée sous ce nom de fichier."""


class InvalidImageError(ImageError):
    """Fichier dont le contenu n'est pas une image lisible."""


class ImageInUseError(ImageError):
    """Image utilisée par au moins une note : elle ne peut pas être supprimée."""
