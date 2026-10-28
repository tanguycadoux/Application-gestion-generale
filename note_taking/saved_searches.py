"""Recherches enregistrées (#203) : une requête gardée sous un nom.

Le nom est unique sans tenir compte de la casse ni des accents (comparé en Python
avec `core.tables.fold` : le `LOWER` de SQLite ne replie que l'ASCII). Seul le texte
de la zone de recherche est gardé, tel qu'écrit.
"""

from urllib.parse import urlencode

from django.urls import reverse

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


def save_search(name: str, q: str) -> SavedSearch:
    name = clean_name(name)
    q = q.strip()
    if not q:
        raise SavedSearchError("Rien à enregistrer : la zone de recherche est vide.")
    return SavedSearch.objects.create(name=name, q=q)


def rename_search(search: SavedSearch, name: str) -> SavedSearch:
    search.name = clean_name(name, renaming=search)
    search.save(update_fields=["name"])
    return search


def all_searches() -> list[SavedSearch]:
    """Les recherches enregistrées par nom, sans casse ni accents."""
    return sorted(SavedSearch.objects.all(), key=lambda search: fold(search.name))


def query_url(q: str) -> str:
    """La page de recherche pour ce texte (la page seule si le texte est vide)."""
    url = reverse("note_taking:notes_search")
    return f"{url}?{urlencode({'q': q})}" if q else url


def search_url(search: SavedSearch) -> str:
    return query_url(search.q)
