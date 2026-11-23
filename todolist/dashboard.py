"""Blocs de l'accueil général : tâches en retard ou à échéance proche (#233), et
« À traiter » (#384)."""

from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any

from django.db.models import Count, Q, QuerySet
from django.utils import timezone

from note_taking.models import Note, Passage

from .models import SOON_DAYS, Task

# Au-delà, l'accueil renvoie à la liste : un retard accumulé ne doit pas l'envahir.
SHOWN = 10


def due_tasks() -> dict:
    """Tâches en cours dont l'échéance est passée ou sous `SOON_DAYS` jours (le
    même seuil que le signal `soon`), les plus urgentes d'abord, `SHOWN` au plus."""
    limit = timezone.localdate() + timedelta(days=SOON_DAYS)
    tasks = (
        Task.objects.filter(done=False, due_date__lte=limit)
        .select_related("project")
        .order_by("due_date", "pk")
    )
    total = tasks.count()
    return {"tasks": list(tasks[:SHOWN]), "others": max(total - SHOWN, 0)}


@dataclass
class ReviewNote:
    """Une note qui a des tâches à revoir : son bilan les attend."""

    date: date
    count: int
    # Dont les cases du texte sans projet (#385), à rattacher à un projet.
    unfiled: int


@dataclass
class Rubric:
    """Une rubrique du bloc « À traiter » : ses lignes (`SHOWN` au plus) et son total."""

    items: list[Any]
    total: int

    @property
    def others(self) -> int:
        return max(self.total - len(self.items), 0)


def pending() -> dict:
    """Bloc « À traiter » (#384) : ce qu'on a noté vite revient tant qu'on ne s'en
    est pas occupé. Un rappel, pas un blocage. Chaque rubrique, la plus ancienne
    d'abord (ce qui attend depuis le plus longtemps) :

    - tâches à revoir, par note (vers son bilan) ;
    - tâches en cours sans échéance, ni déclarée voulue, ni à revoir (le bilan
      règle leur échéance) ;
    - texte sans projet : les notes qui en ont (#385) ;
    - tâches en cours sans projet hors du bilan : une case du texte sans projet
      reste à revoir tant qu'on ne lui a pas choisi de projet, elle est donc dans la
      première rubrique ; restent les tâches saisies ou modifiées sans projet.
    """
    review = (
        Task.objects.filter(
            created_from_note=True,
            note_state=Task.NoteState.TO_REVIEW,
            note_date__in=Note.objects.values("date"),
        )
        .values("note_date")
        .annotate(
            count=Count("pk"), unfiled=Count("pk", filter=Q(project__isnull=True))
        )
        .order_by("note_date")
    )
    review_notes = [
        ReviewNote(row["note_date"], row["count"], row["unfiled"]) for row in review
    ]
    open_tasks = Task.objects.filter(done=False).exclude(
        note_state=Task.NoteState.TO_REVIEW
    )
    undated = open_tasks.filter(due_date__isnull=True, no_due_date=False)
    rubrics = {
        "review": Rubric(review_notes[:SHOWN], len(review_notes)),
        "undated": rubric(
            undated.select_related("project").order_by("created_at", "pk")
        ),
        "unfiled_text": rubric(
            Note.objects.filter(
                pk__in=Passage.objects.filter(project__isnull=True).values("note")
            ).order_by("date")
        ),
        "unfiled_tasks": rubric(
            open_tasks.filter(project__isnull=True).order_by("created_at", "pk")
        ),
    }
    return {
        **rubrics,
        "review_tasks": sum(note.count for note in review_notes),
        "empty": not any(item.total for item in rubrics.values()),
    }


def rubric(queryset: QuerySet) -> Rubric:
    return Rubric(list(queryset[:SHOWN]), queryset.count())
