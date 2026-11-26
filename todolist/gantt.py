"""Frise de type Gantt d'une tâche et de ses sous-tâches (#168), ou des tâches d'un
projet (#205).

La tâche observée en première ligne, puis une ligne par descendant, indentée,
dans l'ordre du tableau des sous-tâches. Chaque barre
va de la création de la tâche à son échéance ; sans échéance, jusqu'à sa date de
complétion si elle est terminée, sinon jusqu'à aujourd'hui (bord ouvert). L'axe va
de la création la plus ancienne à la date la plus tardive parmi les barres,
l'échéance de la tâche observée et aujourd'hui ; quand aujourd'hui est loin après
tout le reste, l'axe s'arrête avant, et un repère « Aujourd'hui → » le dit (#186).
Les positions sont des pourcentages de l'axe, arrondis au dixième.
"""

from dataclasses import dataclass, field
from datetime import date

from django.template.defaultfilters import date as format_date
from django.utils import timezone

from core.month_calendar import shift_month

from .models import Task
from .tree import TaskRow, descendant_rows

# Aujourd'hui est « loin » après la dernière date de la frise au-delà de ce nombre de
# jours et de cette part de sa longueur : l'axe s'arrête alors à cette date (#186).
FAR_DAYS = 14
FAR_SHARE = 0.25

# Repères de mois selon la largeur de la frise (#185), en rem : largeur supposée
# sous chaque palier d'une requête de conteneur, et classes qui montrent un repère à
# partir de ce palier. Un repère prend environ LABEL_REM (« sept. », et son trait).
TICK_WIDTHS = (10, 20, 32, 48)
TICK_VISIBILITY = (
    "",
    "hidden @min-[20rem]:block",
    "hidden @min-[32rem]:block",
    "hidden @min-[48rem]:block",
    "hidden",
)
LABEL_REM = 2.75
# Un mois sur 1, 3, 6 ou 12 : chaque pas divise le suivant, un repère gardé sur une
# frise étroite l'est donc aussi sur une plus large.
TICK_STEPS = (1, 3, 6, 12)


@dataclass
class GanttRow:
    task: Task
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
class Tick:
    label: str
    position: float
    # Classes qui le cachent quand la frise est trop étroite (#185).
    visibility: str = ""


@dataclass
class GanttChart:
    start: date
    end: date
    rows: list[GanttRow]
    # Position d'aujourd'hui ; None quand l'axe s'arrête avant (`today_beyond`).
    today: float | None
    parent_due: float | None
    # La tâche observée ; aucune pour la frise d'un projet.
    task: Task | None = None
    ticks: list[Tick] = field(default_factory=list)
    today_beyond: bool = False
    today_date: date | None = None


def gantt_chart(task: Task, today: date | None = None) -> GanttChart | None:
    """Frise des descendants de `task` ; None s'il n'en a pas."""
    descendants = descendant_rows(task)
    if not descendants:
        return None
    rows = [TaskRow(task, 0, True)] + [
        TaskRow(row.task, row.level + 1, row.has_children) for row in descendants
    ]
    return rows_chart(rows, task, today)


def rows_chart(
    rows: list[TaskRow], task: Task | None = None, today: date | None = None
) -> GanttChart | None:
    """Frise de ces lignes ; avec `task`, celle de la tâche observée, dont l'échéance
    est marquée. None sans ligne."""
    if not rows:
        return None
    today = today or timezone.localdate()
    due = task.due_date if task else None

    spans = []
    for row in rows:
        begin = timezone.localdate(row.task.created_at)
        finish = row.task.due_date or completion(row.task) or today
        spans.append((row, min(begin, finish), max(begin, finish)))

    start = min(begin for _, begin, _ in spans)
    last = max([finish for _, _, finish in spans] + [due or start])
    gap = (today - last).days
    today_beyond = gap > FAR_DAYS and gap > FAR_SHARE * (last - start).days
    end = last if today_beyond else max(last, today)
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
                open_end=row.task.due_date is None and completion(row.task) is None,
            )
        )

    return GanttChart(
        start=start,
        end=end,
        rows=gantt_rows,
        today=None if today_beyond else position(today),
        parent_due=position(due) if due else None,
        task=task,
        ticks=month_ticks(start, end, position),
        today_beyond=today_beyond,
        today_date=today,
    )


def completion(task: Task) -> date | None:
    """Date de complétion d'une tâche terminée, None sinon."""
    if task.done and task.completed_at:
        return timezone.localdate(task.completed_at)
    return None


def month_ticks(start: date, end: date, position) -> list[Tick]:
    """Début de chaque mois de l'axe. Sur plusieurs années, janvier porte l'année.

    Quand la place manque, un mois sur 3, 6 ou 12 seulement (#185) : pour chaque
    palier de largeur, le plus petit pas qui laisse à chaque repère sa place.
    """
    months_rem = [width * 30.44 / max((end - start).days, 1) for width in TICK_WIDTHS]
    steps = [
        next((step for step in TICK_STEPS if step * rem >= LABEL_REM), TICK_STEPS[-1])
        for rem in months_rem
    ]
    several_years = start.year != end.year
    ticks = []
    month = date(start.year, start.month, 1)
    while month <= end:
        shown = [(month.month - 1) % step == 0 for step in steps]
        label = str(month.year) if several_years and month.month == 1 else None
        ticks.append(
            Tick(
                label=label or format_date(month, "N"),
                position=max(position(month), 0.0),
                visibility=TICK_VISIBILITY[shown.index(True) if True in shown else 4],
            )
        )
        month = shift_month(month.year, month.month, 1)
    return ticks
