from django.db import models

from core.models import Project, Subject, Tag


class Note(models.Model):
    date = models.DateField(unique=True)
    body = models.TextField(blank=True, default="")

    created = models.DateTimeField(auto_now_add=True)
    updated = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.date}"

    @property
    def projects(self):
        return Project.objects.filter(note_parts__note=self).distinct()


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
    content = models.TextField(blank=True, null=True, default=None)

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

        return render_note_part(self.content or "")


class NotePartImage(models.Model):
    file = models.ImageField(upload_to="note_images/", blank=True, null=True)
    original_path = models.CharField(max_length=255, unique=True)

    def __str__(self):
        return self.file.name
