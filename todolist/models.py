from datetime import date
from typing import TYPE_CHECKING

from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator
from django.db import models
from django.db.models import Q
from django.db.models.signals import post_delete
from django.dispatch import receiver

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
    # Terminée : suit l'avancement (100 %) pour une tâche sans sous-tâche ; se
    # coche à la main pour un parent, et se décoche dès qu'un de ses enfants
    # n'est plus terminé (#164).
    done = models.BooleanField("terminée", default=False)

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

    # Ancêtres dont l'avancement a changé au dernier enregistrement (#164).
    updated_ancestor_ids: list[int]

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

        old_parent_id = None
        if self.pk:
            old_parent_id = (
                Todo.objects.filter(pk=self.pk)
                .values_list("parent_id", flat=True)
                .first()
            )
            # L'avancement d'un parent se calcule, il ne se saisit pas (#164).
            computed = self.children_progress()
            if computed is not None:
                self.progress = computed
        if not self.pk or not self.children.exists():
            self.done = self.progress == 100

        super().save(*args, **kwargs)

        self.updated_ancestor_ids = update_ancestors_progress(self.parent_id)
        if old_parent_id not in (None, self.parent_id):
            update_ancestors_progress(old_parent_id)

    def children_progress(self) -> int | None:
        """Moyenne arrondie de l'avancement des enfants ; None sans enfant."""
        values = list(self.children.values_list("progress", flat=True))
        if not values:
            return None
        return round(sum(values) / len(values))

    @property
    def completed(self) -> bool:
        return self.done

    @property
    def to_validate(self) -> bool:
        """Parent dont tous les enfants sont terminés, pas encore coché."""
        return self.progress == 100 and not self.done

    def clean(self):
        if self.parent:
            ancestor = self.parent
            while ancestor:
                if ancestor == self:
                    raise ValidationError(
                        "Impossible de créer une boucle dans les sous-tâches."
                    )
                ancestor = ancestor.parent

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


def update_ancestors_progress(parent_id: int | None) -> list[int]:
    """Recalcule l'avancement des ancêtres, du parent jusqu'à la racine (#164).

    Un parent coché se décoche dès qu'un de ses enfants n'est plus terminé ; un
    parent sans plus d'enfant garde ses dernières valeurs. Renvoie les
    identifiants des tâches modifiées.
    """
    updated = []
    while parent_id is not None:
        parent = Todo.objects.filter(pk=parent_id).first()
        if parent is None:
            break
        computed = parent.children_progress()
        if computed is None:
            break
        done = parent.done and not parent.children.filter(done=False).exists()
        if (computed, done) == (parent.progress, parent.done):
            break
        Todo.objects.filter(pk=parent.pk).update(progress=computed, done=done)
        updated.append(parent.pk)
        parent_id = parent.parent_id
    return updated


@receiver(post_delete, sender=Todo)
def update_progress_after_delete(sender, instance: Todo, **kwargs):
    update_ancestors_progress(instance.parent_id)
