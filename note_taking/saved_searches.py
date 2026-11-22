"""Recherches enregistrées (#203) : une requête gardée sous un nom.

Le nom est unique sans tenir compte de la casse ni des accents (comparé en Python
avec `core.tables.fold` : le `LOWER` de SQLite ne replie que l'ASCII). On garde le
texte de la zone de recherche, tel qu'écrit, et les cases cochées de l'arbre (#380).
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from urllib.parse import urlencode

from django.http import QueryDict
from django.urls import reverse

from core.models import Project, Section
from core.tables import fold

from .exceptions import SavedSearchError
from .models import SavedSearch

NAME_MAX_LENGTH: int = SavedSearch._meta.get_field("name").max_length  # type: ignore[assignment]


def clean_name(name: str, renaming: SavedSearch | None = None) -> str:
    """Le nom nettoyé, ou `SavedSearchError`. `renaming` : la recherche renommée,
    qui peut garder son nom ou n'en changer que la casse."""
    name = " ".join(name.split())
    if not name:
        raise SavedSearchError("Donner un nom à la recherche.")
    if len(name) > NAME_MAX_LENGTH:
        raise SavedSearchError(
            f"Le nom d'une recherche tient en {NAME_MAX_LENGTH} caractères au plus."
        )
    others = SavedSearch.objects.all()
    if renaming:
        others = others.exclude(pk=renaming.pk)
    if any(fold(other.name) == fold(name) for other in others):
        raise SavedSearchError(f"Une recherche nommée « {name} » existe déjà.")
    return name


@dataclass
class Filters:
    """Ce qui fait une recherche dans l'adresse : `?q=…&projects=…&subjects=…`."""

    q: str = ""
    projects: list[int] = field(default_factory=list)
    subjects: list[int] = field(default_factory=list)

    def __bool__(self) -> bool:
        return bool(self.q or self.projects or self.subjects)

    @classmethod
    def read(cls, data: QueryDict) -> Filters:
        """D'une adresse ou d'un formulaire ; une clé qui n'est pas un nombre est
        ignorée."""
        return cls(
            data.get("q", "").strip(),
            ids(data.getlist("projects")),
            ids(data.getlist("subjects")),
        )

    def url(self) -> str:
        """La page de recherche pour ces filtres (la page seule s'il n'y en a pas)."""
        pairs = [("q", self.q)] if self.q else []
        pairs += [("projects", str(pk)) for pk in self.projects]
        pairs += [("subjects", str(pk)) for pk in self.subjects]
        url = reverse("note_taking:notes_search")
        return f"{url}?{urlencode(pairs)}" if pairs else url


def ids(values: Iterable[object]) -> list[int]:
    """Les clés distinctes et triées parmi ces valeurs, les autres ignorées."""
    return sorted({int(str(v)) for v in values if str(v).isdigit()})


def save_search(
    name: str, q: str, projects: Iterable[object] = (), sections: Iterable[object] = ()
) -> SavedSearch:
    """Enregistre le texte et les cases cochées ; une case inconnue est ignorée."""
    name = clean_name(name)
    q = q.strip()
    chosen_projects = list(Project.objects.filter(pk__in=ids(projects)))
    chosen_sections = list(Section.objects.filter(pk__in=ids(sections)))
    if not (q or chosen_projects or chosen_sections):
        raise SavedSearchError(
            "Rien à enregistrer : la zone de recherche est vide et aucune case "
            "n'est cochée."
        )
    saved = SavedSearch.objects.create(name=name, q=q)
    saved.projects.set(chosen_projects)
    saved.sections.set(chosen_sections)
    return saved


def rename_search(search: SavedSearch, name: str) -> SavedSearch:
    search.name = clean_name(name, renaming=search)
    search.save(update_fields=["name"])
    return search


def all_searches() -> list[SavedSearch]:
    """Les recherches enregistrées par nom, sans casse ni accents."""
    searches = SavedSearch.objects.prefetch_related("projects", "sections")
    return sorted(searches, key=lambda search: fold(search.name))


def filters_of(search: SavedSearch) -> Filters:
    return Filters(
        search.q,
        ids(project.pk for project in search.projects.all()),
        ids(section.pk for section in search.sections.all()),
    )


def search_url(search: SavedSearch) -> str:
    return filters_of(search).url()
