from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Count, Q
from django.db.models.functions import Lower
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


class Section(models.Model):
    """Niveau d'un chemin sous un projet (#287, #295) : « Réunion › Préparation »
    est la section « Préparation », fille de « Réunion », sous le projet.

    Un arbre de lignes plutôt qu'un texte à séparateurs : un « / » dans un titre
    ne peut pas passer pour un séparateur, et renommer un niveau fait suivre ses
    descendants. Un niveau est unique sous son parent, casse ignorée
    (`core/sections.py`). Les parents existent parce que ce sont de vraies lignes.
    """

    project = models.ForeignKey(
        Project,
        verbose_name="projet",
        on_delete=models.CASCADE,
        related_name="sections",
    )
    parent = models.ForeignKey(
        "self",
        verbose_name="niveau parent",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="children",
    )
    name = models.CharField("nom", max_length=200)

    class Meta:
        verbose_name = "section"
        ordering = ["name"]
        constraints = [
            # Un parent absent ne compte pas comme une valeur pour l'unicité :
            # deux contraintes, selon qu'il y en a un ou non.
            models.UniqueConstraint(
                Lower("name"),
                "project",
                condition=Q(parent__isnull=True),
                name="unique_root_section",
            ),
            models.UniqueConstraint(
                Lower("name"),
                "parent",
                condition=Q(parent__isnull=False),
                name="unique_child_section",
            ),
        ]

    def __str__(self):
        from .sections import label

        return label(self)

    def clean(self):
        if self.parent_id and self.parent.project_id != self.project_id:
            raise ValidationError("Le niveau parent est celui d'un autre projet.")


class Tag(models.Model):
    """Tag, partagé par les note parts et les TODO."""

    name = models.CharField(max_length=200, unique=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name
