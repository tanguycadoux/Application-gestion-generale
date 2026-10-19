from pathlib import Path

from django.db import models
from django.utils import timezone

VECTOR_EXTENSIONS = {".svg"}


class Image(models.Model):
    """Image utilisable dans les notes, référencée par son nom de fichier.

    Le format (vectoriel ou matriciel) se déduit du fichier, et l'origine
    (importée ou créée dans l'application) de la présence d'une source.
    """

    # Nom de fichier d'origine, tel qu'écrit dans les notes : ![…](dossier/<name>)
    name = models.CharField(max_length=255, unique=True)
    # Fichier affiché.
    file = models.ImageField(upload_to="note_images/", max_length=255)
    # Fichier éditable, pour les images créées avec l'éditeur d'images.
    source = models.FileField(upload_to="image_sources/", max_length=255, blank=True)

    created_at = models.DateTimeField(default=timezone.now, editable=False)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name

    @property
    def is_vector(self) -> bool:
        return Path(self.file.name or "").suffix.lower() in VECTOR_EXTENSIONS

    @property
    def is_editable(self) -> bool:
        """Image créée dans l'application, modifiable à partir de sa source."""
        return bool(self.source)
