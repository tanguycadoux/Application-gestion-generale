"""Bloc des tâches en retard ou à échéance proche de l'accueil général (#233)."""

from datetime import timedelta

from django.utils import timezone

from .models import SOON_DAYS, Todo

# Au-delà, l'accueil renvoie à la liste : un retard accumulé ne doit pas l'envahir.
SHOWN = 10


def due_tasks() -> dict:
    """Tâches en cours dont l'échéance est passée ou sous `SOON_DAYS` jours (le
    même seuil que le signal `soon`), les plus urgentes d'abord, `SHOWN` au plus."""
    limit = timezone.localdate() + timedelta(days=SOON_DAYS)
    tasks = (
        Todo.objects.filter(done=False, due_date__lte=limit)
        .select_related("project")
        .order_by("due_date", "pk")
    )
    total = tasks.count()
    return {"tasks": list(tasks[:SHOWN]), "others": max(total - SHOWN, 0)}
