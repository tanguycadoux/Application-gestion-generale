"""Grille d'un calendrier mensuel, partagée par les apps (#88, #167).

La grille ne connaît que les jours ; chaque app fournit son type de case
(`day_class`, sous-classe de `CalendarDay`) et la remplit avec ses données.
"""

import calendar
from dataclasses import dataclass, field
from datetime import date

from django.utils import timezone

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


# Un mois occupe au plus six semaines (du lundi au dimanche).
MAX_WEEKS = 6


@dataclass
class CalendarDay:
    date: date
    in_month: bool
    is_today: bool
    is_weekend: bool
    is_future: bool = False


@dataclass
class MonthCalendar:
    month: date
    weeks: list[list]
    previous: date
    next: date
    weekday_labels: list[tuple[str, str]] = field(
        default_factory=lambda: list(WEEKDAY_LABELS)
    )

    @property
    def spare_weeks(self) -> range:
        """Les lignes à réserver sous un mois de moins de six semaines (#275) : la
        hauteur du calendrier ne change pas d'un mois à l'autre."""
        return range(MAX_WEEKS - len(self.weeks))

    def days(self) -> list:
        return [day for week in self.weeks for day in week]

    @property
    def first(self) -> date:
        return self.weeks[0][0].date

    @property
    def last(self) -> date:
        return self.weeks[-1][-1].date


def month_grid(
    year: int, month: int, today: date, day_class: type = CalendarDay
) -> MonthCalendar:
    """Mois en semaines du lundi au dimanche, avec des cases vides de `day_class`."""
    weeks = calendar.Calendar(firstweekday=calendar.MONDAY).monthdatescalendar(
        year, month
    )
    return MonthCalendar(
        month=date(year, month, 1),
        weeks=[
            [
                day_class(
                    date=day,
                    in_month=day.month == month,
                    is_today=day == today,
                    is_weekend=day.weekday() >= calendar.SATURDAY,
                    is_future=day > today,
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


def requested_month(month_param: str) -> tuple[date, int, int]:
    """Date du jour, année et mois demandés (AAAA-MM), le mois courant sinon."""
    today = timezone.localdate()
    year, month = parse_month_param(month_param) or (today.year, today.month)
    return today, year, month
