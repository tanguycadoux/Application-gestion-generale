"""Images collées ou déposées depuis le presse-papiers ou le bureau (#196).

Le navigateur envoie un fichier sans vrai nom (« image.png ») : on lui en donne un,
horodaté, que le renommage d'une image permettra de changer. `note_taking` s'en
charge parce que les pages d'images y sont ; `images` ne connaît toujours pas les
notes.
"""

from collections.abc import Container
from datetime import datetime

from django.core.files.uploadedfile import UploadedFile
from django.utils import timezone

from images.exceptions import InvalidImageError
from images.models import Image
from images.services import import_image

EXTENSIONS = {
    "image/png": ".png",
    "image/jpeg": ".jpg",
    "image/gif": ".gif",
    "image/webp": ".webp",
    "image/bmp": ".bmp",
    "image/svg+xml": ".svg",
}


def capture_name(extension: str, now: datetime, taken: Container[str]) -> str:
    """`capture-AAAA-MM-JJ-HHMMSS.png`, suivi de `-2`, `-3`… si ce nom est pris."""
    base = f"capture-{now:%Y-%m-%d-%H%M%S}"
    name = f"{base}{extension}"
    number = 2
    while name in taken:
        name = f"{base}-{number}{extension}"
        number += 1
    return name


def import_capture(file: UploadedFile, now: datetime | None = None) -> Image:
    """Importe une capture sous un nom généré ; le contenu est vérifié comme à
    l'import (`images.services.import_image`)."""
    extension = EXTENSIONS.get(file.content_type or "")
    if extension is None:
        raise InvalidImageError(
            f"Ce type de fichier n'est pas une image prise en charge\xa0: "
            f"{file.content_type or 'inconnu'}."
        )
    taken = set(
        Image.objects.filter(name__startswith="capture-").values_list("name", flat=True)
    )
    file.name = capture_name(extension, now or timezone.localtime(), taken)
    return import_image(file)
