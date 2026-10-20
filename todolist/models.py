from datetime import date
from typing import TYPE_CHECKING

from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator
from django.db import models
from django.db.models import Q

from core.models import Project, Subject, Tag

if TYPE_CHECKING:
    from django.db.models import QuerySet


class Todo(models.Model):
    PRIORITY_CHOICES = [
        ("low", "Basse"),
        ("medium", "Moyenne"),
        ("high", "Haute"),
    ]

    title = models.CharField("titre", max_length=200)
    project = models.ForeignKey(
        Project,
        verbose_name="projet",
        on_delete=models.PROTECT,
        related_name="todos",
    )
    subject = models.ForeignKey(
        Subject,
        verbose_name="sujet",
        on_delete=models.PROTECT,
        related_name="todos",
        null=True,
        blank=True,
    )
    tags = models.ManyToManyField(
        Tag, verbose_name="tags", related_name="todos", blank=True
    )
    description = models.TextField("description", blank=True)
    # Avancement en pourcentage (#163) ; une tâche est terminée à 100 %.
    progress = models.PositiveSmallIntegerField(
        "avancement (%)", default=0, validators=[MaxValueValidator(100)]
    )

    created_from_note = models.BooleanField(default=False)
    note_part_date = models.DateField(null=True, blank=True)
    note_part_text = models.CharField(max_length=200, blank=True, default="")

    priority = models.CharField(
        "priorité", max_length=10, choices=PRIORITY_CHOICES, default="medium"
    )

    due_date = models.DateField("échéance", null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    parent = models.ForeignKey(
        "self",
        verbose_name="tâche parente",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="children",
    )

    if TYPE_CHECKING:
        children: QuerySet[Todo]

    class Meta:
        verbose_name = "tâche"
        constraints = [
            models.UniqueConstraint(
                fields=["created_from_note", "note_part_date", "note_part_text"],
                condition=Q(created_from_note=True),
                name="unique_note_parts_when_created_from_note",
            )
        ]

    def __str__(self):
        return self.title

    def save(self, *args, **kwargs):
        # Le parent propose son projet et son échéance (formulaire), il ne les
        # impose pas : les écarts sont signalés, pas empêchés. Seule la boucle
        # parent-enfant est refusée.
        self.clean()
        super().save(*args, **kwargs)

    @property
    def completed(self) -> bool:
        return self.progress == 100

    def clean(self):
        if self.parent:
            ancestor = self.parent
            while ancestor:
                if ancestor == self:
                    raise ValidationError(
                        "Impossible de créer une boucle dans les sous-tâches."
                    )
                ancestor = ancestor.parent

    def set_completed(self, completed: bool) -> list[int]:
        """Passe la tâche à 100 % ou à 0 % ; la compléter complète aussi ses
        sous-tâches.

        Renvoie les identifiants des tâches modifiées.
        """
        self.progress = 100 if completed else 0
        self.save()
        toggled_ids = [self.pk]

        if completed:
            for child in self.children.all():
                toggled_ids += child.set_completed(True)
        return toggled_ids

    @property
    def due_status(self):
        if not self.due_date or self.completed:
            return None

        today = date.today()
        delta = (self.due_date - today).days

        if delta < 0:
            return "overdue"
        elif delta == 0:
            return "today"
        elif delta <= 3:
            return "soon"
        return "normal"
