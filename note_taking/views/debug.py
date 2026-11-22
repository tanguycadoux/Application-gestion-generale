"""Pages de développement (#235) : l'analyse d'une note en JSON, 404 sans `DEBUG`."""

from django.conf import settings
from django.http import Http404, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render

from core.dates import parse_date_param

from ..models import Note
from ..qmd.parser import parse_note


def debug_note_json(request):
    """Choisir la note dont on veut l'analyse en JSON (#235) ; mène à `note_json`."""
    if not settings.DEBUG:
        raise Http404
    day = parse_date_param(request.GET.get("date", ""))
    if day is not None:
        return redirect("note_taking:note_json", note_date=day)
    return render(request, "note_taking/debug_note_json.html")


def note_json(request, note_date):
    if not settings.DEBUG:
        raise Http404
    note = get_object_or_404(Note, date=note_date)
    return JsonResponse(parse_note(str(note.date), note.body).as_dict())
