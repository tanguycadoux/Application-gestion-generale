"""Services des images : import et suppression."""

from functools import partial
from pathlib import Path
from xml.etree import ElementTree

from django.db import transaction
from django.db.models import ProtectedError
from PIL import Image as PILImage

from .exceptions import ImageAlreadyExistsError, ImageInUseError, InvalidImageError
from .models import VECTOR_EXTENSIONS, Image

SVG_ROOT_TAGS = {"svg", "{http://www.w3.org/2000/svg}svg"}


def import_image(file) -> Image:
    """Importe un fichier image ; son nom sert de référence dans les notes."""
    if Image.objects.filter(name=file.name).exists():
        raise ImageAlreadyExistsError(
            f"Une image avec ce nom de fichier existe déjà\xa0: {file.name}"
        )
    check_image_file(file)

    return Image.objects.create(name=file.name, file=file)


def check_image_file(file) -> None:
    """Vérifie que le contenu est une image (#224) : SVG dont la racine est <svg>,
    ou image matricielle lisible par Pillow. L'extension seule ne suffit pas."""
    if Path(file.name).suffix.lower() in VECTOR_EXTENSIONS:
        valid = is_svg(file)
    else:
        valid = is_raster_image(file)
    file.seek(0)
    if not valid:
        raise InvalidImageError(
            f"Le fichier {file.name} n'est pas une image lisible\xa0: il n'a pas "
            "été importé."
        )


def is_svg(file) -> bool:
    try:
        root = ElementTree.fromstring(file.read())
    except ElementTree.ParseError:
        return False
    return root.tag in SVG_ROOT_TAGS


def is_raster_image(file) -> bool:
    try:
        with PILImage.open(file) as image:
            image.verify()
    except OSError, SyntaxError, ValueError, PILImage.DecompressionBombError:
        return False
    return True


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
