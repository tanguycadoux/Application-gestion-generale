"""Vues des recherches enregistrées (#203) : créer, renommer, supprimer.

Toutes en POST, puis retour à la page de recherche. La recherche en cours voyage dans
l'adresse (`?q=…&projects=…&subjects=…`, #380) : on la retrouve telle qu'elle était,
même après une erreur (nom déjà pris, par exemple).
"""

from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect
from django.views.decorators.http import require_POST

from core.exceptions import AppError

from ..models import SavedSearch
from ..saved_searches import Filters, rename_search, save_search, search_url


def back_to_search(request):
    return redirect(Filters.read(request.GET).url())


@require_POST
def create_saved_search(request):
    filters = Filters.read(request.POST)
    try:
        saved = save_search(
            request.POST.get("name", ""),
            filters.q,
            filters.projects,
            filters.subjects,
        )
    except AppError as e:
        messages.error(request, str(e))
        return redirect(filters.url())
    messages.success(request, f"La recherche « {saved.name} » est enregistrée.")
    return redirect(search_url(saved))


@require_POST
def rename_saved_search(request, pk: int):
    saved = get_object_or_404(SavedSearch, pk=pk)
    try:
        rename_search(saved, request.POST.get("name", ""))
    except AppError as e:
        messages.error(request, str(e))
    else:
        messages.success(request, f"La recherche « {saved.name} » est renommée.")
    return back_to_search(request)


@require_POST
def delete_saved_search(request, pk: int):
    saved = get_object_or_404(SavedSearch, pk=pk)
    saved.delete()
    messages.success(request, f"La recherche « {saved.name} » est supprimée.")
    return back_to_search(request)
