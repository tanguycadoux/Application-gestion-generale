"""Frise de type Gantt d'une tâche et de ses sous-tâches (#168).

La tâche observée en première ligne, puis une ligne par descendant, indentée,
dans l'ordre du tableau des sous-tâches. Chaque barre
va de la création de la tâche à son échéance, ou jusqu'à aujourd'hui sans
échéance (bord ouvert). L'axe va de la création la plus ancienne à la date la
plus tardive parmi les échéances, celle du parent et aujourd'hui. Les positions
sont des pourcentages de l'axe, arrondis au dixième.
"""

from dataclasses import dataclass, field
from datetime import date

from django.template.defaultfilters import date as format_date
from django.utils import timezone

from core.month_calendar import shift_month

from .models import Todo
from .tree import TaskRow, descendant_rows


@dataclass
class GanttRow:
    task: Todo
    level: int
    begin: date
    finish: date
    start: float
    width: float
    open_end: bool

    @property
    def progress(self) -> int:
        return self.task.progress


@dataclass
class GanttChart:
    start: date
    end: date
    rows: list[GanttRow]
    today: float
    parent_due: float | None
    ticks: list[tuple[str, float]] = field(default_factory=list)


def gantt_chart(task: Todo, today: date | None = None) -> GanttChart | None:
    """Frise des descendants de `task` ; None s'il n'en a pas."""
    today = today or timezone.localdate()
    descendants = descendant_rows(task)
    if not descendants:
        return None
    rows = [TaskRow(task, 0, True)] + [
        TaskRow(row.task, row.level + 1, row.has_children) for row in descendants
    ]

    spans = []
    for row in rows:
        begin = timezone.localdate(row.task.created_at)
        finish = row.task.due_date or today
        spans.append((row, min(begin, finish), max(begin, finish)))

    start = min(begin for _, begin, _ in spans)
    end = max([finish for _, _, finish in spans] + [today, task.due_date or today])
    length = max((end - start).days, 1)

    def position(day: date) -> float:
        return round((day - start).days / length * 100, 1)

    gantt_rows = []
    for row, begin, finish in spans:
        left = position(begin)
        gantt_rows.append(
            GanttRow(
                task=row.task,
                level=row.level,
                begin=begin,
                finish=finish,
                start=left,
                width=round(position(finish) - left, 1),
                open_end=row.task.due_date is None,
            )
        )

    return GanttChart(
        start=start,
        end=end,
        rows=gantt_rows,
        today=position(today),
        parent_due=position(task.due_date) if task.due_date else None,
        ticks=month_ticks(start, end, position),
    )


def month_ticks(start: date, end: date, position) -> list[tuple[str, float]]:
    """Début de chaque mois de l'axe : (abréviation, position)."""
    ticks = []
    month = date(start.year, start.month, 1)
    while month <= end:
        ticks.append((format_date(month, "N"), max(position(month), 0.0)))
        month = shift_month(month.year, month.month, 1)
    return ticks
