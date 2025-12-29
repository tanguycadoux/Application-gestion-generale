from typing import Any
from django.contrib import messages
from django.db.models.query import QuerySet
from django.http import Http404, JsonResponse
from django.shortcuts import render, redirect, get_object_or_404
from django.views.generic import ListView, DetailView

from pathlib import Path
import markdown

from .models import Note, Project
from .utils import insert_note_in_table, parse_note_as_dict


def index(request):
    context = {}

    return render(request, "note_taking/index.html", context)


class NoteDetail(DetailView):
    model = Note

class NoteList(ListView):
    model = Note
    context_object_name = "notes"

    DEFAULT_ORDERING = "-date"
    
    def get_queryset(self):
        qs = super().get_queryset()

        sort = self.request.GET.get("sort")
        direction = self.request.GET.get("direction")

        if not sort or not direction:
            return qs.order_by(self.DEFAULT_ORDERING)

        ordering = sort if direction == "asc" else f"-{sort}"
        return qs.order_by(ordering)
    

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        sort = self.request.GET.get("sort")
        direction = self.request.GET.get("direction")
        if not sort or not direction:
            next_direction = "asc"
            next_sort = self.DEFAULT_ORDERING.lstrip("-")
        elif direction == "asc":
            next_direction = "desc"
            next_sort = sort
        else:
            next_direction = None
            next_sort = None

        context.update({
            "sort": sort,
            "direction": direction,
            "next_sort": next_sort,
            "next_direction": next_direction,
        })
        return context


class ProjectDetail(DetailView):
    model = Project
    context_object_name = "project"

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        context = super().get_context_data(**kwargs)
        note_parts = self.object.note_parts.all().order_by('-note__date')
        dates = note_parts.values_list('note__date', flat=True).distinct()
        context["note_parts_by_date"] = []
        for date in dates:
            note_parts_date = note_parts.filter(note__date=date)
            context["note_parts_by_date"].append((date, note_parts_date))
        return context

class ProjectList(ListView):
    model = Project


def note_md(request, pk):
    note = get_object_or_404(Note, pk=pk)
    
    if note.raw is not None:
        html_content = markdown.markdown(note.raw, extensions=["fenced_code", "tables"])    
    else:
        html_content = "<p>Aucun contenu disponible.</p>"
    
    context = {
        "date": note.date,
        "content": html_content,
    }

    return render(request, "note_taking/note_md.html", context)

def import_note(request):
    if request.method == "POST":
        try:
            files = request.FILES.getlist("note_import")
            for file in files:
                insert_note_in_table(file)
            messages.success(request, "Les notes sont ajoutées.")
        except Exception as e:
            messages.error(request, f"Erreur lors de l'ajout de la note : {e}")
    return redirect(request.META.get('HTTP_REFERER', '/'))

def note_json(request, pk):
    note = get_object_or_404(Note, pk=pk)
    return JsonResponse(parse_note_as_dict(note))

# ADMIN
def clear_notes(request):
    Note.objects.all().delete()

    return redirect(request.META.get('HTTP_REFERER', '/'))
