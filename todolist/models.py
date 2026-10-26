from dataclasses import dataclass
from typing import TYPE_CHECKING

from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator
from django.db import models
from django.db.models import Q
from django.db.models.signals import post_delete
from django.dispatch import receiver
from django.utils import timezone

from core.models import Project, Subject, Tag
from core.templatetags.ui import date_text

if TYPE_CHECKING:
    from django.db.models import QuerySet


# Titre et texte d'origine d'une tâche : une ligne de note longue doit tenir (#222).
TODO_TEXT_MAX_LENGTH = 500


# Seuil de l'échéance proche, en jours (ambre).
SOON_DAYS = 3


class TodoManager(models.Manager):
    """Tâches affichées : sans les tâches écartées (#240)."""

    def get_queryset(self):
        return super().get_queryset().exclude(note_state=Todo.NoteState.DISMISSED)


def protect_unless_dismissed(collector, field, sub_objs, using):
    """Un projet utilisé par une tâche est protégé ; ses tâches écartées, que plus
    rien n'affiche, sont supprimées avec lui (#240)."""
    dismissed = [obj for obj in sub_objs if obj.note_state == Todo.NoteState.DISMISSED]
    active = [obj for obj in sub_objs if obj.note_state != Todo.NoteState.DISMISSED]
    if active:
        models.PROTECT(collector, field, active, using)
    if dismissed:
        models.CASCADE(collector, field, dismissed, using)


class Todo(models.Model):
    class NoteState(models.TextChoices):
        """Où en est une tâche issue d'une note (#240) ; vide pour une tâche
        saisie à la main."""

        TO_REVIEW = "to_review", "à revoir"
        REVIEWED = "reviewed", "revue"
        DETACHED = "detached", "gardée sans sa ligne"
        DISMISSED = "dismissed", "écartée"

    PRIORITY_CHOICES = [
        ("low", "Basse"),
        ("medium", "Moyenne"),
        ("high", "Haute"),
    ]

    title = models.CharField("titre", max_length=TODO_TEXT_MAX_LENGTH)
    project = models.ForeignKey(
        Project,
        verbose_name="projet",
        on_delete=protect_unless_dismissed,
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
    # Moment où la tâche est passée à terminée ; vide tant qu'elle est en cours
    # (#167, calendrier : une tâche terminée se place à cette date).
    completed_at = models.DateTimeField(
        "terminée le", null=True, blank=True, editable=False
    )
    # Avancement retenu quand la tâche passe à terminée, rendu quand on la
    # décoche (#237) ; 0 pour une tâche créée terminée.
    progress_before_done = models.PositiveSmallIntegerField(default=0, editable=False)

    created_from_note = models.BooleanField(default=False)
    note_part_date = models.DateField(null=True, blank=True)
    note_part_text = models.CharField(
        max_length=TODO_TEXT_MAX_LENGTH, blank=True, default=""
    )
    # Chemin de la ligne dans la note : titres de sa section sans `TODO`, puis
    # lignes parentes, séparés par « › » (#240). Avec la date et le texte, il
    # identifie la tâche ; vide pour une tâche créée avant #240, pas encore reprise.
    note_path = models.TextField(blank=True, default="")
    # À revoir dans le bilan de sa note tant qu'elle n'y a pas été enregistrée,
    # ou quand sa ligne disparaît ; écartée, elle n'est plus affichée ni recréée.
    note_state = models.CharField(
        "état dans sa note",
        max_length=10,
        choices=NoteState.choices,
        blank=True,
        default="",
        editable=False,
    )

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

    # Parent et enfants déjà chargés par l'arbre des tâches (todolist.tree, #188) :
    # les incohérences se calculent alors sans requête.
    tree: tuple[Todo | None, list[Todo]] | None = None

    # Ancêtres dont l'avancement a changé au dernier enregistrement (#164).
    updated_ancestor_ids: list[int]

    # Toutes les tâches, écartées comprises : l'identité des tâches issues des
    # notes les compte, pour ne pas les recréer.
    all_objects = models.Manager()
    objects = TodoManager()

    class Meta:
        verbose_name = "tâche"
        # Sans les tâches écartées : listes, sous-tâches, formulaires (#240).
        default_manager_name = "objects"
        constraints = [
            models.UniqueConstraint(
                fields=[
                    "created_from_note",
                    "note_part_date",
                    "note_path",
                    "note_part_text",
                ],
                condition=Q(created_from_note=True),
                name="unique_note_line_when_created_from_note",
            )
        ]

    def __str__(self):
        return self.title

    def save(self, *args, **kwargs):
        # Le parent propose son projet et son échéance (formulaire), il ne les
        # impose pas : les écarts sont signalés, pas empêchés. Seule la boucle
        # parent-enfant est refusée.
        self.clean()

        old_parent_id, old_progress, was_done = None, 0, False
        if self.pk:
            old_parent_id, old_progress, was_done = (
                Todo.objects.filter(pk=self.pk)
                .values_list("parent_id", "progress", "done")
                .first()
            ) or (None, 0, False)
            # L'avancement d'un parent se calcule, il ne se saisit pas (#164).
            computed = self.children_progress()
            if computed is not None:
                self.progress = computed
        if not self.pk or not self.children.exists():
            self.done = self.progress == 100
            if self.done and not was_done:
                self.progress_before_done = old_progress
        if not self.done:
            self.completed_at = None
        elif self.completed_at is None:
            self.completed_at = timezone.now()

        super().save(*args, **kwargs)

        self.updated_ancestor_ids = update_ancestors_progress(self.parent_id)
        if old_parent_id not in (None, self.parent_id):
            update_ancestors_progress(old_parent_id)

    def descendants_count(self) -> int:
        """Nombre de sous-tâches, à tous les niveaux : supprimées avec la tâche."""
        count, level = 0, [self.pk]
        while level:
            level = list(
                Todo.objects.filter(parent_id__in=level).values_list("pk", flat=True)
            )
            count += len(level)
        return count

    def children_progress(self) -> int | None:
        """Moyenne arrondie de l'avancement des enfants ; None sans enfant."""
        values = list(self.children.values_list("progress", flat=True))
        if not values:
            return None
        return round(sum(values) / len(values))

    @property
    def completed(self) -> bool:
        return self.done

    def incoherences(self) -> list[Incoherence]:
        """Écarts à corriger avec sa tâche parente et ses sous-tâches (#165).

        Rien n'est empêché : ces écarts sont seulement signalés, des deux côtés
        (sur le parent et sur l'enfant), avec un lien vers l'autre tâche.
        """
        parent, children = self.tree or (
            self.parent,
            list(self.children.select_related("project")),
        )
        found = []
        if parent is not None:
            found += pair_incoherences(parent, self, from_parent=False)
        for child in children:
            found += pair_incoherences(self, child, from_parent=True)
        return found

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
    def due_signal(self) -> str:
        """Signal de l'échéance, seule règle d'urgence (#189) : `done` (terminée),
        `overdue` (en retard), `soon` (aujourd'hui ou sous `SOON_DAYS` jours) ou
        `normal` (plus tard, ou sans échéance). Barre d'avancement, temps restant,
        calendrier et frise l'utilisent."""
        if self.done:
            return "done"
        if self.due_date is None:
            return "normal"
        days = (self.due_date - timezone.localdate()).days
        if days < 0:
            return "overdue"
        if days <= SOON_DAYS:
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
        Todo.objects.filter(pk=parent.pk).update(
            progress=computed,
            done=done,
            completed_at=parent.completed_at if done else None,
        )
        updated.append(parent.pk)
        parent_id = parent.parent_id
    return updated


@receiver(post_delete, sender=Todo)
def update_progress_after_delete(sender, instance: Todo, **kwargs):
    update_ancestors_progress(instance.parent_id)


@dataclass
class Incoherence:
    """Écart à corriger, et l'autre tâche concernée (#165)."""

    message: str
    task: Todo


def pair_incoherences(
    parent: Todo, child: Todo, from_parent: bool
) -> list[Incoherence]:
    """Incohérences entre un parent et un de ses enfants, vues de l'un ou de l'autre."""
    found = []
    if parent.due_date and child.due_date and child.due_date > parent.due_date:
        parent_due = date_text(parent.due_date, "moyen")
        child_due = date_text(child.due_date, "moyen")
        found.append(
            Incoherence(
                f"L'échéance de la sous-tâche « {child} » ({child_due}) est après "
                f"celle-ci ({parent_due}).",
                child,
            )
            if from_parent
            else Incoherence(
                f"Son échéance ({child_due}) est après celle de la tâche parente "
                f"« {parent} » ({parent_due}).",
                parent,
            )
        )
    if child.project_id != parent.project_id:
        found.append(
            Incoherence(
                f"La sous-tâche « {child} » a un autre projet ({child.project}).",
                child,
            )
            if from_parent
            else Incoherence(
                f"Son projet ({child.project}) diffère de celui de la tâche parente "
                f"« {parent} » ({parent.project}).",
                parent,
            )
        )
    if parent.done and not child.done:
        found.append(
            Incoherence(
                f"Elle est terminée alors que la sous-tâche « {child} » ne l'est pas.",
                child,
            )
            if from_parent
            else Incoherence(
                f"Elle n'est pas terminée alors que la tâche parente « {parent} » "
                "l'est.",
                parent,
            )
        )
    return found
