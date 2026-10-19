from django.db import models
from django.utils import timezone


class Project(models.Model):
    """Projet, partagé par les notes et les TODO."""

    name = models.CharField(max_length=200, unique=True)
    description = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(default=timezone.now, editable=False)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name
