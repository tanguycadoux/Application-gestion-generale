import tempfile
from datetime import date
from functools import partial

from django.contrib import messages
from django.db.models import Prefetch
from django.http import FileResponse, Http404, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_GET, require_POST
from django.views.generic import DetailView, ListView

from core.exceptions import AppError
from core.sections import with_descendants
from core.suggestions import rank_by_name
from core.templatetags.ui import date_text
from images.exceptions import ImageError
from images.models import Image
from images.services import delete_image as delete_image_service

from . import importing
from .captures import import_capture
from .forms import NewNoteForm, NoteSearchForm
from .models import Note, NotePart
from .note_calendar import requested_month_calendar
from .qmd.export import write_note_archive, write_notes_archive
from .qmd.parser import parse_note
from .rendering import render_note_body
from .services import (
    process_note_parts,
    update_note_from_source_file,
)


def index(request):
    """Accueil : note du jour et calendrier du mois demandé (?month=AAAA-MM)."""
    today, calendar = requested_month_calendar(request.GET.get("month", ""))

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
    slug_field = "date"
    slug_url_kwarg = "note_date"


class NoteList(ListView):
    model = Note
    context_object_name = "notes"

    DEFAULT_ORDERING = "-date"
    # Tris proposés par l'interface ; toute autre valeur revient au tri par défaut (#219).
    SORT_FIELDS = ("date",)
    DIRECTIONS = ("asc", "desc")

    def requested_sort(self) -> tuple[str | None, str | None]:
        sort = self.request.GET.get("sort")
        direction = self.request.GET.get("direction")
        if sort in self.SORT_FIELDS and direction in self.DIRECTIONS:
            return sort, direction
        return None, None

    def get_queryset(self):
        # Projets de chaque note préchargés : une requête pour toute la liste (#188).
        qs = (
            super()
            .get_queryset()
            .prefetch_related(
                Prefetch("parts", queryset=NotePart.objects.select_related("project"))
            )
        )

        sort, direction = self.requested_sort()

        if not sort or not direction:
            return qs.order_by(self.DEFAULT_ORDERING)

        ordering = sort if direction == "asc" else f"-{sort}"
        return qs.order_by(ordering)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        sort, direction = self.requested_sort()
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
    messages.success(request, f"L'image « {name} » est supprimée.")
    return redirect("note_taking:images_list")


# Action d'une ancienne adresse par id -> nom de l'adresse par date.
ID_ACTIONS = {
    "md": "note_md",
    "json": "note_json",
    "export": "export_note",
    "edit": "edit_note",
    "delete": "delete_note",
}


def note_by_id(request, pk, action=""):
    """Les anciennes adresses par id mènent à celle par date (#273).

    Redirection permanente qui garde la méthode (308) : un formulaire envoyé à
    l'ancienne adresse arrive aussi.
    """
    name = ID_ACTIONS.get(action, "") if action else "note_detail"
    if not name:
        raise Http404
    note = get_object_or_404(Note, pk=pk)
    response = HttpResponse(status=308)
    response["Location"] = reverse(f"note_taking:{name}", args=[note.date])
    return response


def note_md(request, note_date):
    note = get_object_or_404(Note, date=note_date)

    if note.body:
        html_content = render_note_body(note.body)
    else:
        html_content = "<p>Aucun contenu disponible.</p>"

    context = {
        "date": note.date,
        "content": html_content,
    }

    return render(request, "note_taking/note_md.html", context)


@require_POST
def import_files(request):
    """Importe notes, images et archives selon leur type, puis le compte rendu."""
    files = request.FILES.getlist("import_files")
    if not files:
        messages.warning(request, "Aucun fichier sélectionné.")
        return redirect("note_taking:notes_list")
    report = importing.import_files(files)
    return render(request, "note_taking/import_report.html", {"report": report})


@require_POST
def update_source_file(request, note_date):
    note = get_object_or_404(Note, date=note_date)
    file = request.FILES.get("note_update_source_file")
    if file is None:
        messages.error(request, "Choisir un fichier.")
    else:
        try:
            update_note_from_source_file(note, file)
        except AppError as e:
            messages.error(request, f"Erreur lors de la mise à jour de la note : {e}")
        else:
            messages.success(request, f"{note_name(note)} est modifiée.")
            if note.warnings:
                messages.warning(request, warnings_message(note.warnings))
    return redirect(next_page(note))


def note_json(request, note_date):
    note = get_object_or_404(Note, date=note_date)
    return JsonResponse(parse_note(str(note.date), note.body).as_dict())


def notes_search(request):
    form = NoteSearchForm(request.POST or None)
    results = None

    if request.method == "POST" and form.is_valid():
        projects = form.cleaned_data["projects"]
        subjects = form.cleaned_data["subjects"]

        results_qs = (
            NotePart.objects.select_related("note", "section")
            .prefetch_related("tags")
            .order_by("-note__date")
        )

        if projects:
            results_qs = results_qs.filter(project__in=projects)

        if subjects:
            sections = with_descendants({int(pk) for pk in subjects})
            results_qs = results_qs.filter(section_id__in=sections)

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


def note_name(note: Note) -> str:
    """« La note du 24 novembre 2025 », pour les messages."""
    return f"La note du {date_text(note.date, 'moyen')}"


def save_note_parts(request, note: Note, done: str) -> str:
    """Recalcule les note parts d'une note enregistrée, et le dit (#192).

    Si l'analyse échoue, seul le message d'erreur s'affiche. Renvoie la page où
    aller ensuite : celle de la note, ou la suite proposée par une autre app,
    comme le bilan des tâches créées (#239).
    """
    try:
        process_note_parts(note)
    except AppError as e:
        messages.error(
            request,
            f"La note est enregistrée mais son contenu n'a pas pu être traité : {e}",
        )
    else:
        messages.success(request, f"{note_name(note)} est {done}.")
        if note.warnings:
            messages.warning(request, warnings_message(note.warnings))
    return next_page(note)


def warnings_message(warnings: tuple[str, ...]) -> str:
    """Le premier avertissement de l'analyse d'une note (titre qui saute un niveau,
    #305), puis le nombre des autres : les lister tous noierait le toast."""
    others = len(warnings) - 1
    if not others:
        return warnings[0]
    plural = "s" if others > 1 else ""
    return f"{warnings[0]} {others} autre{plural} titre{plural} à vérifier."


def next_page(note: Note) -> str:
    """Page après l'enregistrement d'une note : la suite proposée par une autre
    app (#239), sinon la note."""
    if note.follow_ups:
        return note.follow_ups[0].url
    return reverse("note_taking:note_detail", args=[note.date])


def new_note(request):
    if request.method == "POST":
        form = NewNoteForm(request.POST)
        if form.is_valid():
            note = form.save()
            return redirect(save_note_parts(request, note, "créée"))
    else:
        note_date = parse_date_param(request.GET.get("date", ""))
        existing = Note.objects.filter(date=note_date).first() if note_date else None
        if existing:
            return redirect("note_taking:note_detail", note_date=existing.date)
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
        return redirect("note_taking:note_detail", note_date=note.date)
    return redirect(f"{reverse('note_taking:new_note')}?date={today.isoformat()}")


def edit_note(request, note_date):
    note = get_object_or_404(Note, date=note_date)

    if request.method == "POST":
        form = NewNoteForm(request.POST, instance=note)
        if form.is_valid():
            note = form.save()
            return redirect(save_note_parts(request, note, "modifiée"))
    else:
        form = NewNoteForm(instance=note)

    return render(request, "note_taking/note_edit.html", {"form": form, "note": note})


@require_POST
def delete_note(request, note_date):
    """Supprime une note ; la confirmation se fait par popover (data-confirm)."""
    note = get_object_or_404(Note, date=note_date)
    name = note_name(note)
    note.delete()
    messages.success(request, f"{name} est supprimée.")
    return redirect("note_taking:notes_list")


def export_notes(request):
    """Télécharge l'archive zip de toutes les notes et de leurs images."""
    return zip_response(write_notes_archive, f"notes-{timezone.localdate()}.zip")


def export_note(request, note_date):
    """Télécharge l'archive zip d'une note et des images qu'elle référence."""
    note = get_object_or_404(Note, date=note_date)
    return zip_response(partial(write_note_archive, note), f"{note.date}.zip")


def zip_response(write, filename: str) -> FileResponse:
    """Réponse de téléchargement d'une archive écrite par `write(fichier)`."""
    archive = tempfile.SpooledTemporaryFile(max_size=10 * 1024 * 1024)
    write(archive)
    archive.seek(0)
    return FileResponse(
        archive, as_attachment=True, filename=filename, content_type="application/zip"
    )


@require_GET
def image_suggestions(request):
    """Les images, pour les suggestions de l'éditeur (#90) : la référence à écrire
    dans la note et l'adresse de la vignette ; `?q=` filtre par nom."""
    images = rank_by_name(
        Image.objects.all(), request.GET.get("q", ""), lambda image: image.name
    )
    return JsonResponse(
        {
            "results": [
                {
                    "name": image.name,
                    "reference": f"images/{image.name}",
                    "url": image.file.url,
                }
                for image in images
            ]
        }
    )


@require_POST
def image_capture(request):
    """Importe une image collée ou déposée (#196) : l'éditeur insère la référence
    renvoyée ; la page des images se recharge ensuite (`notify`) et y affiche le
    message de succès ou de refus."""
    notify = bool(request.POST.get("notify"))

    def refuse(text: str):
        if notify:
            messages.error(request, text)
        return JsonResponse({"error": text}, status=400)

    file = request.FILES.get("image")
    if file is None:
        return refuse("Aucune image reçue.")
    try:
        image = import_capture(file)
    except ImageError as e:
        return refuse(str(e))
    if notify:
        messages.success(request, f"L'image « {image.name} » est importée.")
    return JsonResponse(
        {
            "name": image.name,
            "reference": f"images/{image.name}",
            "url": image.file.url,
        },
        status=201,
    )
