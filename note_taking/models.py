from django.db import models

from core.models import Project, Subject, Tag
from images.models import Image

from .signals import NoteFollowUp


class Note(models.Model):
    date = models.DateField(unique=True)
    body = models.TextField(blank=True, default="")

    created = models.DateTimeField(auto_now_add=True)
    updated = models.DateTimeField(auto_now=True)

    # Suites proposées par les autres apps au dernier recalcul des note parts
    # (#239) : tâches créées, par exemple.
    follow_ups: tuple[NoteFollowUp, ...] = ()

    def __str__(self):
        return f"{self.date}"

    @property
    def projects(self):
        """Projets des note parts de la note, par nom.

        Sans requête si les note parts ont été préchargées avec leur projet (#188).
        """
        if "parts" in getattr(self, "_prefetched_objects_cache", {}):
            unique = {part.project_id: part.project for part in self.parts.all()}
            return sorted(unique.values(), key=lambda project: project.name)
        return Project.objects.filter(note_parts__note=self).distinct()

    @property
    def images(self):
        """Images utilisées par les note parts de la note."""
        return Image.objects.filter(note_parts__note=self).distinct()


class NotePart(models.Model):
    note = models.ForeignKey(Note, on_delete=models.CASCADE, related_name="parts")
    project = models.ForeignKey(
        Project, on_delete=models.PROTECT, related_name="note_parts"
    )
    subject = models.ForeignKey(
        Subject,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="note_parts",
    )
    tags = models.ManyToManyField(Tag, related_name="note_parts", blank=True)
    # Images référencées dans le contenu (image:<pk>), recalculées à l'analyse.
    images = models.ManyToManyField(
        Image, through="NotePartImageLink", related_name="note_parts", blank=True
    )
    content = models.TextField(blank=True, default="")

    created = models.DateTimeField(auto_now_add=True)
    updated = models.DateTimeField(auto_now=True)

    def __str__(self):
        string_repr = str(self.project)
        if self.subject:
            string_repr = f"{string_repr}, {self.subject}"
        return string_repr

    def rendered_content(self):
        # Import local : rendering importe les modèles.
        from .rendering import render_note_part

        return render_note_part(self.content)


class NotePartImageLink(models.Model):
    """Utilisation d'une image par une note part.

    Le lien vers l'image est protégé : une image utilisée ne peut pas être
    supprimée.
    """

    note_part = models.ForeignKey(
        NotePart, on_delete=models.CASCADE, related_name="image_links"
    )
    image = models.ForeignKey(
        Image, on_delete=models.PROTECT, related_name="note_part_links"
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["note_part", "image"], name="unique_note_part_image"
            )
        ]

    def __str__(self):
        return f"{self.note_part} → {self.image}"
