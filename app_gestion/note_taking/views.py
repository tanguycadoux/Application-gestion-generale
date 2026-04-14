from typing import Any
from django.contrib import messages
from django.db.models.query import QuerySet
from django.http import Http404, JsonResponse, HttpResponse
from django.shortcuts import render, redirect, get_object_or_404
from django.template.loader import render_to_string
from django.views.generic import ListView, DetailView

from pathlib import Path
import markdown

from .forms import NoteSearchForm
from .models import Note, Project, NotePart, NotePartImage
from .utils import insert_note_in_table, update_note_from_source_file, parse_note_raw_file_as_dict, import_image


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

class NotePartImageList(ListView):
    model = NotePartImage
    context_object_name = "images"
    template_name = "note_taking/images_list.html"


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
            messages.success(request, "Les notes sont ajoutées")
        except Exception as e:
            messages.error(request, f"Erreur lors de l'ajout de la note : {e}")
    return redirect(request.META.get('HTTP_REFERER', '/'))

def update_source_file(request, pk):
    if request.method == "POST":
        try:
            file = request.FILES.get("note_update_source_file")
            if file is None:
                raise ImportError("Choisir un fichier")
            update_note_from_source_file(pk, file)
            messages.success(request, "La note est mise à jour")
        except Exception as e:
            messages.error(request, f"Erreur lors de la mise à jour de la note : {e}")
    return redirect(request.META.get('HTTP_REFERER', '/'))

def note_json(request, pk):
    note = get_object_or_404(Note, pk=pk)
    return JsonResponse(parse_note_raw_file_as_dict(note.date, note.raw))

# ADMIN
def clear_notes(request):
    Note.objects.all().delete()

    return redirect(request.META.get('HTTP_REFERER', '/'))

def notes_search(request):
    form = NoteSearchForm(request.POST or None)
    results = None

    if request.method == "POST" and form.is_valid():
        projects = form.cleaned_data["projects"]
        subjects = form.cleaned_data["subjects"]

        results_qs = NotePart.objects.all()

        if projects:
            results_qs = results_qs.filter(project__in=projects)

        if subjects:
            results_qs = results_qs.filter(subject__in=subjects)
        
        results = []
        for part in results_qs:
            results.append({
                "part": part,
                "html": part.rendered_content
            })
    
    if request.htmx:
        html = render_to_string("note_taking/notes_search_result.html", {
            "results": results
        })
        return HttpResponse(html)

    return render(request, "note_taking/notes_search.html", {
        "form": form,
        "results": results,
    })

def get_subjects(request):
    form = NoteSearchForm(request.POST or None)

    projects = request.POST.getlist("projects")

    if projects:
        subjects = (
            NotePart.objects
            .filter(project_id__in=projects)
            .exclude(subject__isnull=True)
            .exclude(subject__exact="")
            .values_list("subject", flat=True)
            .distinct()
        )
    else:
        subjects = (
            NotePart.objects
            .exclude(subject__isnull=True)
            .exclude(subject__exact="")
            .values_list("subject", flat=True)
            .distinct()
        )

    form.fields["subjects"].choices = [(s, s) for s in sorted(subjects, key=str.lower)]

    html = render_to_string("note_taking/subjects_block.html", {"form": form})
    return HttpResponse(html)

def import_images(request):
    if request.method == "POST":
        try:
            files = request.FILES.getlist("image_import")
            for file in files:
                import_image(file)
            messages.success(request, "Les images sont ajoutées")
        except Exception as e:
            messages.error(request, f"Erreur lors de l'ajout de l'image : {e}")
    return redirect(request.META.get('HTTP_REFERER', '/'))
