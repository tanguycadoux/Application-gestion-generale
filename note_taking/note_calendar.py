"""Calendrier mensuel des notes (#88), sur la grille partagée de core (#167)."""

from dataclasses import dataclass, field
from datetime import date

from core.month_calendar import CalendarDay, MonthCalendar, month_grid, requested_month

from .models import Note, NotePart


@dataclass
class NoteCalendarDay(CalendarDay):
    note: Note | None = None
    projects: list[str] = field(default_factory=list)

    @property
    def can_create(self) -> bool:
        """Une note peut être créée pour un jour passé ou aujourd'hui, sans note."""
        return self.note is None and self.in_month and not self.is_future


def month_calendar(year: int, month: int, today: date) -> MonthCalendar:
    """Mois en semaines du lundi au dimanche, avec les notes et leurs projets."""
    calendar = month_grid(year, month, today, day_class=NoteCalendarDay)
    period = (calendar.first, calendar.last)

    notes = {note.date: note for note in Note.objects.filter(date__range=period)}
    projects: dict[date, list[str]] = {}
    for note_date, name in (
        NotePart.objects.filter(note__date__range=period)
        .values_list("note__date", "project__name")
        .distinct()
        .order_by("note__date", "project__name")
    ):
        projects.setdefault(note_date, []).append(name)

    for day in calendar.days():
        day.note = notes.get(day.date)
        day.projects = projects.get(day.date, [])
    return calendar


def requested_month_calendar(month_param: str) -> tuple[date, MonthCalendar]:
    """Date du jour et calendrier du mois demandé (AAAA-MM), le mois courant sinon."""
    today, year, month = requested_month(month_param)
    return today, month_calendar(year, month, today)
