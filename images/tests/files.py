"""Fichiers d'image valides pour les tests (#224 : l'import vérifie le contenu)."""

import io

from django.core.files.uploadedfile import SimpleUploadedFile
from PIL import Image as PILImage
from PIL.PngImagePlugin import PngInfo


def png(label: str = "") -> bytes:
    """PNG de 1 × 1 pixel ; `label`, écrit dans ses métadonnées, le distingue."""
    info = PngInfo()
    info.add_text("label", label)
    buffer = io.BytesIO()
    PILImage.new("RGB", (1, 1), "white").save(buffer, "PNG", pnginfo=info)
    return buffer.getvalue()


def image_file(name: str, label: str = "") -> SimpleUploadedFile:
    return SimpleUploadedFile(name, png(label), content_type="image/png")
