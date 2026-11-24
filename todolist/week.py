"""Les tâches d'une semaine : terminées, créées, en retard, pour son bilan (#208)."""

from django.db.models import Q, QuerySet
from django.utils import timezone

from core.weeks import Week

from .models import Task


def week_tasks(week: Week) -> dict:
    """Une requête par rubrique. Les moments se comparent à l'heure locale
    (`Week.start`, `Week.end`) ; les tâches écartées sont exclues."""
    tasks = Task.objects.select_related("project")
    late = late_tasks(tasks, week)
    return {
        "week": week,
        "done": list(
            tasks.filter(
                done=True, completed_at__gte=week.start, completed_at__lt=week.end
            ).order_by("completed_at", "pk")
        ),
        "created": list(
            tasks.filter(created_at__gte=week.start, created_at__lt=week.end).order_by(
                "created_at", "pk"
            )
        ),
        # None pour une semaine à venir : son retard ne se sait pas encore.
        "late": None if late is None else list(late.order_by("due_date", "pk")),
    }


def late_tasks(tasks: QuerySet[Task], week: Week) -> QuerySet[Task] | None:
    """Les tâches en retard **à la fin de la semaine**, ou aujourd'hui pour la semaine
    en cours ; rien pour une semaine à venir.

    Pour une semaine passée : échéance au plus tard le dimanche, tâche déjà créée, et
    pas terminée ce dimanche-là (elle a pu l'être depuis). L'échéance est celle
    d'aujourd'hui : ses changements ne sont pas gardés.
    """
    if week.is_future:
        return None
    if week.is_current:
        return tasks.filter(done=False, due_date__lt=timezone.localdate())
    return tasks.filter(
        Q(done=False) | Q(completed_at__gte=week.end),
        due_date__lte=week.sunday,
        created_at__lt=week.end,
    )
