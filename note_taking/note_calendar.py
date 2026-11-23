"""Calendrier mensuel des notes (#88), sur la grille partagée de core (#167)."""

from dataclasses import dataclass, field
from datetime import date

from core.models import Project
from core.month_calendar import CalendarDay, MonthCalendar, month_grid, requested_month

from .models import Note, Passage


@dataclass
class NoteCalendarDay(CalendarDay):
    note: Note | None = None
    # Projets des passages de la note, par nom ; le texte sans projet n'en a pas.
    projects: list[Project] = field(default_factory=list)

    @property
    def can_create(self) -> bool:
        """Une note peut être créée pour un jour passé ou aujourd'hui, sans note."""
        return self.note is None and self.in_month and not self.is_future


def month_calendar(year: int, month: int, today: date) -> MonthCalendar:
    """Mois en semaines du lundi au dimanche, avec les notes et leurs projets."""
    calendar = month_grid(year, month, today, day_class=NoteCalendarDay)
    period = (calendar.first, calendar.last)

    notes = {note.date: note for note in Note.objects.filter(date__range=period)}
    # Les projets eux-mêmes, pour leur couleur (#378) : une requête pour le mois.
    projects: dict[date, list[Project]] = {}
    seen: set[tuple[date, int]] = set()
    for passage in (
        Passage.objects.filter(note__date__range=period, project__isnull=False)
        .select_related("note", "project")
        .order_by("note__date", "project__name")
    ):
        key = (passage.note.date, passage.project_id)
        if key not in seen:
            seen.add(key)
            projects.setdefault(passage.note.date, []).append(passage.project)

    for day in calendar.days():
        day.note = notes.get(day.date)
        day.projects = projects.get(day.date, [])
    return calendar


def requested_month_calendar(month_param: str) -> tuple[date, MonthCalendar]:
    """Date du jour et calendrier du mois demandé (AAAA-MM), le mois courant sinon."""
    today, year, month = requested_month(month_param)
    return today, month_calendar(year, month, today)
