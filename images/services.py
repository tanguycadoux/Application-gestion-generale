"""Services des images : import."""

from .exceptions import ImageAlreadyExistsError
from .models import Image


def import_image(file) -> Image:
    """Importe un fichier image ; son nom sert de référence dans les notes."""
    if Image.objects.filter(name=file.name).exists():
        raise ImageAlreadyExistsError(
            f"Une image avec ce nom de fichier existe déjà\xa0: {file.name}"
        )

    return Image.objects.create(name=file.name, file=file)
