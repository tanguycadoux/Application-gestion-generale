"""Une semaine, du lundi au dimanche, pour son bilan (#208).

Elle s'écrit comme la norme ISO : `2026-W48`. L'année est celle de la semaine, qui
peut différer de celle du jour : le 29 décembre 2025 est dans `2026-W01`.
"""

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta

from django.template.defaultfilters import date as format_date
from django.utils import timezone

from .dates import date_text

# Années acceptées dans l'adresse : loin des bornes du calendrier de Python, où la
# semaine d'à côté ne s'écrit plus.
FIRST_YEAR, LAST_YEAR = 1900, 2999


@dataclass(frozen=True)
class Week:
    monday: date

    @classmethod
    def of(cls, day: date) -> Week:
        """La semaine de ce jour."""
        return cls(day - timedelta(days=day.weekday()))

    @classmethod
    def parse(cls, slug: str) -> Week:
        """La semaine `AAAA-WNN` ; `ValueError` si elle n'existe pas (une année a 52
        ou 53 semaines)."""
        year, number = (int(part) for part in slug.split("-W"))
        if not FIRST_YEAR <= year <= LAST_YEAR:
            raise ValueError(f"Année hors de portée : {year}")
        return cls(date.fromisocalendar(year, number, 1))

    @property
    def year(self) -> int:
        return self.monday.isocalendar().year

    @property
    def number(self) -> int:
        return self.monday.isocalendar().week

    @property
    def slug(self) -> str:
        return f"{self.year}-W{self.number:02}"

    @property
    def sunday(self) -> date:
        return self.monday + timedelta(days=6)

    @property
    def start(self) -> datetime:
        """Le lundi à minuit, à l'heure locale : compris."""
        return timezone.make_aware(datetime.combine(self.monday, time.min))

    @property
    def end(self) -> datetime:
        """Le lundi suivant à minuit, à l'heure locale : exclu."""
        return timezone.make_aware(
            datetime.combine(self.monday + timedelta(days=7), time.min)
        )

    @property
    def is_current(self) -> bool:
        return self == Week.of(timezone.localdate())

    @property
    def is_future(self) -> bool:
        return self.monday > timezone.localdate()

    @property
    def previous(self) -> Week | None:
        return self._shifted(-7)

    @property
    def next(self) -> Week | None:
        return self._shifted(7)

    def _shifted(self, days: int) -> Week | None:
        week = Week(self.monday + timedelta(days=days))
        return week if FIRST_YEAR <= week.year <= LAST_YEAR else None

    @property
    def label(self) -> str:
        """« du 24 au 30 novembre 2025 », le mois et l'année du lundi s'ils diffèrent."""
        first, last = self.monday, self.sunday
        if first.year != last.year:
            start = date_text(first, "moyen")
        else:
            start = "1er" if first.day == 1 else str(first.day)
            if first.month != last.month:
                start += f" {format_date(first, 'F')}"
        return f"du {start} au {date_text(last, 'moyen')}"
