"""Calendrier mensuel des tâches (#167), sur la grille partagée de core.

Une tâche en cours se place à son échéance, une tâche terminée à sa date de
complétion.
"""

from dataclasses import dataclass, field
from datetime import date

from django.db.models import Q
from django.utils import timezone

from core.month_calendar import CalendarDay, MonthCalendar, month_grid

from .models import Todo

# Au-delà, une case affiche « + N autres ».
VISIBLE_TASKS = 3


@dataclass
class TaskCalendarDay(CalendarDay):
    tasks: list[Todo] = field(default_factory=list)

    @property
    def visible_tasks(self) -> list[Todo]:
        return self.tasks[:VISIBLE_TASKS]

    @property
    def more(self) -> int:
        return max(len(self.tasks) - VISIBLE_TASKS, 0)

    @property
    def can_create(self) -> bool:
        """Une tâche peut être créée avec une échéance sur tout jour du mois."""
        return self.in_month


def calendar_date(task: Todo) -> date | None:
    """Date de la tâche dans le calendrier : complétion si terminée, échéance sinon."""
    if task.done:
        return timezone.localdate(task.completed_at) if task.completed_at else None
    return task.due_date


def task_calendar(year: int, month: int, today: date) -> MonthCalendar:
    calendar = month_grid(year, month, today, day_class=TaskCalendarDay)
    days = {day.date: day for day in calendar.days()}

    # Les terminées sont filtrées sur leur date locale de complétion ci-dessous.
    tasks = Todo.objects.select_related("project").filter(
        Q(done=False, due_date__range=(calendar.first, calendar.last))
        | Q(done=True, completed_at__isnull=False)
    )
    for task in sorted(tasks, key=lambda task: (task.project.name, task.title.lower())):
        when = calendar_date(task)
        if when in days:
            days[when].tasks.append(task)
    return calendar
