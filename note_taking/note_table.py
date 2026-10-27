"""Tri et filtres du tableau des notes (#178), sur les composants de `core.tables`."""

from django.db.models import F, QuerySet

from core.models import Project
from core.tables import (
    Choice,
    ChoiceFilter,
    Column,
    DateRangeFilter,
    Filters,
    Sort,
    Sorting,
)

# Les notes se trient par date ; la plus récente d'abord, comme le premier clic.
SORTING = Sorting(
    {"date": Column(F("date"), descending_first=True)},
    default=Sort("date", descending=True),
)


def filter_dates(notes: QuerySet, value) -> QuerySet:
    start, end = value
    if start:
        notes = notes.filter(date__gte=start)
    if end:
        notes = notes.filter(date__lte=end)
    return notes


def filter_project(notes: QuerySet, name: str) -> QuerySet:
    # `distinct` : une note qui a plusieurs parties du projet ne compte qu'une fois.
    return notes.filter(parts__project__name=name).distinct()


def project_choices() -> list[Choice]:
    """Les projets qui ont au moins une note, avec leur pastille."""
    projects = Project.objects.filter(note_parts__isnull=False).distinct()
    return [Choice(p.name, p.name, p) for p in projects.order_by("name")]


FILTERS = Filters(
    {
        "date": [DateRangeFilter("date", "Date", filter_dates)],
        "projects": [
            ChoiceFilter("project", "Projet", project_choices, filter_project)
        ],
    }
)
