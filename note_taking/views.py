import tempfile
from datetime import date
from functools import partial

from django.contrib import messages
from django.http import FileResponse, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST
from django.views.generic import DetailView, ListView

from core.exceptions import AppError
from images.models import Image
from images.services import delete_image as delete_image_service
from images.services import import_image

from .forms import NewNoteForm, NoteSearchForm
from .models import Note, NotePart
from .note_calendar import requested_month_calendar
from .qmd.archive_import import import_notes_archive
from .qmd.export import write_note_archive, write_notes_archive
from .qmd.parser import parse_note
from .rendering import render_note_body
from .services import (
    insert_note_in_table,
    process_note_parts,
    update_note_from_source_file,
)


def index(request):
    """Accueil : note du jour et calendrier du mois demandé (?mois=AAAA-MM)."""
    today, calendar = requested_month_calendar(request.GET.get("mois", ""))

    return render(
        request,
        "note_taking/index.html",
        {
            "today": today,
            "today_note": Note.objects.filter(date=today).first(),
            "calendar": calendar,
        },
    )


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

        context.update(
            {
                "sort": sort,
                "direction": direction,
                "next_sort": next_sort,
                "next_direction": next_direction,
            }
        )
        return context


class ImageList(ListView):
    model = Image
    context_object_name = "images"
    template_name = "note_taking/images_list.html"


class ImageDetail(DetailView):
    model = Image
    context_object_name = "image"
    template_name = "note_taking/image_detail.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["notes"] = (
            Note.objects.filter(parts__images=self.object).distinct().order_by("date")
        )
        return context


@require_POST
def delete_image(request, pk):
    """Supprime une image inutilisée ; une image utilisée est refusée."""
    image = get_object_or_404(Image, pk=pk)
    name = image.name
    try:
        delete_image_service(image)
    except AppError as e:
        messages.error(request, str(e))
        return redirect("note_taking:image_detail", pk=pk)
    messages.success(request, f"L'image {name} a été supprimée.")
    return redirect("note_taking:images_list")


def note_md(request, pk):
    note = get_object_or_404(Note, pk=pk)

    if note.body:
        html_content = render_note_body(note.body)
    else:
        html_content = "<p>Aucun contenu disponible.</p>"

    context = {
        "date": note.date,
        "content": html_content,
    }

    return render(request, "note_taking/note_md.html", context)


def import_files(request, files, import_file, success_message):
    """Importe chaque fichier indépendamment et affiche un message récapitulatif."""
    imported = 0
    for file in files:
        try:
            import_file(file)
        except AppError as e:
            messages.error(request, f"Échec pour {file.name} : {e}")
        else:
            imported += 1

    if imported:
        messages.success(request, success_message(imported))
    elif not files:
        messages.warning(request, "Aucun fichier sélectionné.")


def import_note(request):
    if request.method == "POST":
        import_files(
            request,
            request.FILES.getlist("note_import"),
            insert_note_in_table,
            lambda n: f"{n} note(s) importée(s).",
        )
    return redirect(request.META.get("HTTP_REFERER", "/"))


@require_POST
def import_archive(request):
    """Réimporte une archive de notes et affiche le compte rendu."""
    file = request.FILES.get("archive_import")
    if file is None:
        messages.warning(request, "Choisir une archive.")
        return redirect("note_taking:notes_list")
    try:
        report = import_notes_archive(file)
    except AppError as e:
        messages.error(request, f"Échec pour {file.name} : {e}")
        return redirect("note_taking:notes_list")
    return render(request, "note_taking/archive_import_report.html", {"report": report})


def update_source_file(request, pk):
    note = get_object_or_404(Note, pk=pk)
    if request.method == "POST":
        file = request.FILES.get("note_update_source_file")
        if file is None:
            messages.error(request, "Choisir un fichier.")
        else:
            try:
                update_note_from_source_file(note, file)
            except AppError as e:
                messages.error(
                    request, f"Erreur lors de la mise à jour de la note : {e}"
                )
            else:
                messages.success(request, "La note est mise à jour.")
    return redirect(request.META.get("HTTP_REFERER", "/"))


def note_json(request, pk):
    note = get_object_or_404(Note, pk=pk)
    return JsonResponse(parse_note(str(note.date), note.body).as_dict())


def notes_search(request):
    form = NoteSearchForm(request.POST or None)
    results = None

    if request.method == "POST" and form.is_valid():
        projects = form.cleaned_data["projects"]
        subjects = form.cleaned_data["subjects"]

        results_qs = (
            NotePart.objects.select_related("note", "subject")
            .prefetch_related("tags")
            .order_by("-note__date")
        )

        if projects:
            results_qs = results_qs.filter(project__in=projects)

        if subjects:
            results_qs = results_qs.filter(subject__name__in=subjects)

        results = list(results_qs)

    if request.htmx:
        html = render_to_string(
            "note_taking/notes_search_result.html", {"results": results}
        )
        return HttpResponse(html)

    return render(
        request,
        "note_taking/notes_search.html",
        {
            "form": form,
            "results": results,
        },
    )


def get_subjects(request):
    form = NoteSearchForm(projects=request.POST.getlist("projects"))

    html = render_to_string("note_taking/subjects_block.html", {"form": form})
    return HttpResponse(html)


def import_images(request):
    if request.method == "POST":
        import_files(
            request,
            request.FILES.getlist("image_import"),
            import_image,
            lambda n: f"{n} image(s) importée(s).",
        )
    return redirect(request.META.get("HTTP_REFERER", "/"))


def new_note(request):
    if request.method == "POST":
        form = NewNoteForm(request.POST)
        if form.is_valid():
            note = form.save()
            try:
                process_note_parts(note)
            except AppError as e:
                messages.error(
                    request,
                    f"La note est enregistrée mais son contenu n'a pas pu être "
                    f"traité : {e}",
                )
            return redirect("note_taking:note_detail", pk=note.pk)
    else:
        note_date = parse_date_param(request.GET.get("date", ""))
        existing = Note.objects.filter(date=note_date).first() if note_date else None
        if existing:
            return redirect("note_taking:note_detail", pk=existing.pk)
        form = NewNoteForm(initial={"date": note_date} if note_date else None)
    return render(request, "note_taking/note_new.html", {"form": form})


def parse_date_param(value: str) -> date | None:
    """Date au format AAAA-MM-JJ, ou None si la valeur n'en est pas une."""
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


def note_today(request):
    """Ouvre la note du jour, ou le formulaire de création à la date du jour."""
    today = timezone.localdate()
    note = Note.objects.filter(date=today).first()
    if note:
        return redirect("note_taking:note_detail", pk=note.pk)
    return redirect(f"{reverse('note_taking:new_note')}?date={today.isoformat()}")


def edit_note(request, pk):
    note = get_object_or_404(Note, pk=pk)

    if request.method == "POST":
        form = NewNoteForm(request.POST, instance=note)
        if form.is_valid():
            note = form.save()
            try:
                process_note_parts(note)
            except AppError as e:
                messages.error(
                    request,
                    f"La note est enregistrée mais son contenu n'a pas pu être "
                    f"traité : {e}",
                )
            return redirect("note_taking:note_detail", pk=note.pk)
    else:
        form = NewNoteForm(instance=note)

    return render(request, "note_taking/note_edit.html", {"form": form, "note": note})


def delete_note(request, pk):
    note = get_object_or_404(Note, pk=pk)
    if request.method == "POST":
        note.delete()
        messages.success(request, "La note a été supprimée.")
        return redirect("note_taking:notes_list")
    return render(request, "note_taking/note_confirm_delete.html", {"note": note})


def export_notes(request):
    """Télécharge l'archive zip de toutes les notes et de leurs images."""
    return zip_response(write_notes_archive, f"notes-{timezone.localdate()}.zip")


def export_note(request, pk):
    """Télécharge l'archive zip d'une note et des images qu'elle référence."""
    note = get_object_or_404(Note, pk=pk)
    return zip_response(partial(write_note_archive, note), f"{note.date}.zip")


def zip_response(write, filename: str) -> FileResponse:
    """Réponse de téléchargement d'une archive écrite par `write(fichier)`."""
    archive = tempfile.SpooledTemporaryFile(max_size=10 * 1024 * 1024)
    write(archive)
    archive.seek(0)
    return FileResponse(
        archive, as_attachment=True, filename=filename, content_type="application/zip"
    )
