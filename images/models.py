from django.db import models
from django.utils import timezone


class Image(models.Model):
    """Image utilisable dans les notes, référencée par son nom de fichier."""

    class Kind(models.TextChoices):
        IMPORTED = "imported", "Importée"
        VECTOR = "vector", "Vectorielle"
        RASTER = "raster", "Matricielle"

    # Nom de fichier d'origine, tel qu'écrit dans les notes : ![…](dossier/<name>)
    name = models.CharField(max_length=255, unique=True)
    kind = models.CharField(max_length=20, choices=Kind.choices, default=Kind.IMPORTED)
    # Fichier affiché.
    file = models.ImageField(upload_to="note_images/", max_length=255)
    # Fichier éditable (dessin vectoriel ou matriciel), pour l'éditeur d'images.
    source = models.FileField(upload_to="image_sources/", max_length=255, blank=True)

    created_at = models.DateTimeField(default=timezone.now, editable=False)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name
