"""Vues des recherches enregistrées (#203) : créer, renommer, supprimer.

Toutes en POST, puis retour à la page de recherche. Le texte de la recherche en cours
voyage dans l'adresse (`?q=…`) : on la retrouve telle qu'elle était, même après une
erreur (nom déjà pris, par exemple).
"""

from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect
from django.views.decorators.http import require_POST

from core.exceptions import AppError

from .models import SavedSearch
from .saved_searches import query_url, rename_search, save_search


def back_to_search(request):
    return redirect(query_url(request.GET.get("q", "")))


@require_POST
def create_saved_search(request):
    q = request.POST.get("q", "")
    try:
        saved = save_search(request.POST.get("name", ""), q)
    except AppError as e:
        messages.error(request, str(e))
        return redirect(query_url(q))
    messages.success(request, f"La recherche « {saved.name} » est enregistrée.")
    return redirect(query_url(saved.q))


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
