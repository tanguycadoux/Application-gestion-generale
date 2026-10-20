"""Services des images : import et suppression."""

from functools import partial

from django.db import transaction
from django.db.models import ProtectedError

from .exceptions import ImageAlreadyExistsError, ImageInUseError
from .models import Image


def import_image(file) -> Image:
    """Importe un fichier image ; son nom sert de référence dans les notes."""
    if Image.objects.filter(name=file.name).exists():
        raise ImageAlreadyExistsError(
            f"Une image avec ce nom de fichier existe déjà\xa0: {file.name}"
        )

    return Image.objects.create(name=file.name, file=file)


def delete_image(image: Image) -> None:
    """Supprime une image inutilisée, avec ses fichiers.

    Une image utilisée est protégée en base (`on_delete=PROTECT`) : le refus
    de Django devient une erreur métier. Les fichiers ne sont effacés qu'une
    fois la suppression validée, pour ne jamais laisser d'image sans fichier.
    """
    files = [(f.storage, f.name) for f in (image.file, image.source) if f.name]
    try:
        with transaction.atomic():
            image.delete()
            for storage, name in files:
                transaction.on_commit(partial(storage.delete, name))
    except ProtectedError:
        raise ImageInUseError(
            f"L'image {image.name} est utilisée par des notes : elle ne peut pas "
            "être supprimée."
        ) from None
