"""Calendrier mensuel des notes, construit côté serveur (#88)."""

import calendar
from dataclasses import dataclass, field
from datetime import date

from django.utils import timezone

from .models import Note, NotePart

# Jours de la semaine, du lundi au dimanche : (abréviation, nom complet).
WEEKDAY_LABELS = [
    ("Lun", "lundi"),
    ("Mar", "mardi"),
    ("Mer", "mercredi"),
    ("Jeu", "jeudi"),
    ("Ven", "vendredi"),
    ("Sam", "samedi"),
    ("Dim", "dimanche"),
]


@dataclass
class CalendarDay:
    date: date
    in_month: bool
    is_today: bool
    is_weekend: bool
    is_future: bool = False
    note: Note | None = None
    projects: list[str] = field(default_factory=list)

    @property
    def can_create(self) -> bool:
        """Une note peut être créée pour un jour passé ou aujourd'hui, sans note."""
        return self.note is None and self.in_month and not self.is_future


@dataclass
class MonthCalendar:
    month: date
    weeks: list[list[CalendarDay]]
    previous: date
    next: date
    weekday_labels: list[tuple[str, str]] = field(
        default_factory=lambda: list(WEEKDAY_LABELS)
    )


def month_calendar(year: int, month: int, today: date) -> MonthCalendar:
    """Mois en semaines du lundi au dimanche, avec les notes et leurs projets."""
    weeks = calendar.Calendar(firstweekday=calendar.MONDAY).monthdatescalendar(
        year, month
    )
    first, last = weeks[0][0], weeks[-1][-1]

    notes = {note.date: note for note in Note.objects.filter(date__range=(first, last))}
    projects: dict[date, list[str]] = {}
    for note_date, name in (
        NotePart.objects.filter(note__date__range=(first, last))
        .values_list("note__date", "project__name")
        .distinct()
        .order_by("note__date", "project__name")
    ):
        projects.setdefault(note_date, []).append(name)

    return MonthCalendar(
        month=date(year, month, 1),
        weeks=[
            [
                CalendarDay(
                    date=day,
                    in_month=day.month == month,
                    is_today=day == today,
                    is_weekend=day.weekday() >= calendar.SATURDAY,
                    is_future=day > today,
                    note=notes.get(day),
                    projects=projects.get(day, []),
                )
                for day in week
            ]
            for week in weeks
        ],
        previous=shift_month(year, month, -1),
        next=shift_month(year, month, 1),
    )


def shift_month(year: int, month: int, delta: int) -> date:
    """Premier jour du mois décalé de `delta` mois."""
    index = year * 12 + (month - 1) + delta
    return date(index // 12, index % 12 + 1, 1)


def parse_month_param(value: str) -> tuple[int, int] | None:
    """Mois au format AAAA-MM, ou None si la valeur n'en est pas un."""
    try:
        parsed = date.fromisoformat(f"{value}-01")
    except ValueError:
        return None
    return parsed.year, parsed.month


def requested_month_calendar(month_param: str) -> tuple[date, MonthCalendar]:
    """Date du jour et calendrier du mois demandé (AAAA-MM), le mois courant sinon."""
    today = timezone.localdate()
    year, month = parse_month_param(month_param) or (today.year, today.month)
    return today, month_calendar(year, month, today)
