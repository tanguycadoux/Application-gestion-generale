from django.db import models
from django.db.models import Count
from django.utils import timezone

# Familles de couleurs Tailwind des projets (#162) : hors gris et hors familles
# qui ont un rôle dans l'interface (blue, red, amber, green).
PROJECT_COLORS = [
    ("orange", "Orange"),
    ("yellow", "Jaune"),
    ("lime", "Citron vert"),
    ("emerald", "Émeraude"),
    ("teal", "Sarcelle"),
    ("cyan", "Cyan"),
    ("sky", "Ciel"),
    ("indigo", "Indigo"),
    ("violet", "Violet"),
    ("purple", "Pourpre"),
    ("fuchsia", "Fuchsia"),
    ("pink", "Rose"),
    ("rose", "Framboise"),
]


def least_used_color() -> str:
    """Famille la moins utilisée par les projets, la première de la liste à égalité."""
    used = dict(
        Project.objects.values_list("color").annotate(count=Count("pk")).order_by()
    )
    return min(
        (used.get(value, 0), index, value)
        for index, (value, _) in enumerate(PROJECT_COLORS)
    )[2]


class Project(models.Model):
    """Projet, partagé par les notes et les tâches."""

    name = models.CharField("nom", max_length=200, unique=True)
    color = models.CharField("couleur", max_length=20, choices=PROJECT_COLORS)
    description = models.TextField("description", blank=True, default="")
    created_at = models.DateTimeField(default=timezone.now, editable=False)

    class Meta:
        verbose_name = "projet"
        ordering = ["name"]

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        # Un projet créé sans couleur (import d'une note, d'une tâche) en reçoit une.
        if not self.color:
            self.color = least_used_color()
        super().save(*args, **kwargs)


class Subject(models.Model):
    """Sujet de note, indépendant des projets."""

    name = models.CharField(max_length=200, unique=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class Tag(models.Model):
    """Tag, partagé par les note parts et les TODO."""

    name = models.CharField(max_length=200, unique=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name
