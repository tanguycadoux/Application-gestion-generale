"""Pages des notes : accueil, tableau, note, création, édition, suppression,
et les anciennes adresses par id (#273)."""

from django.contrib import messages
from django.db.models import Prefetch
from django.http import Http404, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_GET, require_POST
from django.views.generic import DetailView, ListView

from core.dates import date_text, parse_date_param
from core.exceptions import AppError

from .. import note_table
from ..forms import NewNoteForm
from ..models import Note, Passage
from ..note_calendar import requested_month_calendar
from ..note_citations import citations
from ..note_outline import outline_sections
from ..rendering import render_note_body
from ..services import process_passages
from .common import next_page, note_name, save_warnings

# Nombre de notes proposées par l'éditeur après `](` (#206).
SUGGESTED_NOTES = 20


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

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        # Plan de la note et sections repliables (#404).
        layout = outline_sections(render_note_body(self.object.body, heading_ids=True))
        context["content"] = layout.html
        context["outline"] = layout.entries
        # Les notes qui citent celle-ci (#207).
        context["citations"] = citations(self.object)
        return context


class NoteList(ListView):
    """Le tableau des notes : tri (`?sort=`) et filtres (`?project=`, `?date_from=`)
    dans l'URL, côté serveur (#178, `note_table.py`)."""

    model = Note
    context_object_name = "notes"

    def get_queryset(self):
        self.sort = note_table.SORTING.read(self.request.GET.get("sort"))
        self.active_filters = note_table.FILTERS.read(self.request.GET)
        # Projets de chaque note préchargés : une requête pour toute la liste (#188).
        # Le filtre par projet ne cache pas les autres projets d'une note.
        notes = (
            super()
            .get_queryset()
            .prefetch_related(
                Prefetch("passages", queryset=Passage.objects.select_related("project"))
            )
        )
        notes = note_table.FILTERS.apply(notes, self.active_filters)
        return note_table.SORTING.apply(notes, self.sort)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(
            {
                "sorting": note_table.SORTING,
                "sort": self.sort,
                "filters": note_table.FILTERS,
                "active_filters": self.active_filters,
                # L'export prend toutes les notes, filtrées ou non.
                "note_count": Note.objects.count(),
            }
        )
        return context


# Action d'une ancienne adresse par id -> nom de l'adresse par date.
ID_ACTIONS = {
    "md": "note_detail",
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


def save_passages(request, note: Note, done: str, *, stay: bool = False) -> str:
    """Recalcule les passages d'une note enregistrée, et le dit (#192).

    Si l'analyse échoue, seul le message d'erreur s'affiche. Renvoie la page où
    aller ensuite : celle de la note, ou la suite proposée par une autre app,
    comme le bilan des tâches créées (#239). Avec `stay` (#389), l'éditeur de la
    note : la suite proposée n'y mène pas, un avertissement la signale.
    """
    try:
        process_passages(note)
    except AppError as e:
        messages.error(
            request,
            f"La note est enregistrée mais son contenu n'a pas pu être traité : {e}",
        )
    else:
        messages.success(request, f"{note_name(note)} est {done}.")
        save_warnings(request, note)
    if stay:
        for follow_up in note.follow_ups:
            messages.warning(
                request,
                f"{follow_up.label} : le bilan s'ouvrira à la fin de l'édition.",
            )
        return reverse("note_taking:edit_note", args=[note.date])
    return next_page(note)


def stays_in_editor(request) -> bool:
    """Enregistrement par « Enregistrer la note » (ou Ctrl+S), qui reste dans
    l'éditeur, plutôt que par « Terminer l'édition » (#389)."""
    return request.POST.get("stay") == "1"


def toasts_response(request, status: int = 200) -> HttpResponse:
    """Réponse à un enregistrement en arrière-plan (#389) : les messages en
    toasts, rendus par le serveur (#293), que note_form.js ajoute à la page."""
    return render(request, "core/components/message_toasts.html", status=status)


def form_errors_response(request, form) -> HttpResponse:
    """Formulaire refusé lors d'un enregistrement en arrière-plan : chaque erreur
    en toast, et un statut d'erreur pour que le script sache que rien n'est
    enregistré."""
    for errors in form.errors.values():
        for error in errors:
            messages.error(request, f"La note n'est pas enregistrée : {error}")
    return toasts_response(request, status=422)


def new_note(request):
    if request.method == "POST":
        form = NewNoteForm(request.POST)
        if form.is_valid():
            note = form.save()
            stay = stays_in_editor(request)
            return redirect(save_passages(request, note, "créée", stay=stay))
    else:
        note_date = parse_date_param(request.GET.get("date", ""))
        existing = Note.objects.filter(date=note_date).first() if note_date else None
        if existing:
            return redirect("note_taking:note_detail", note_date=existing.date)
        form = NewNoteForm(initial={"date": note_date} if note_date else None)
    return render(request, "note_taking/note_new.html", {"form": form})


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
        stay = stays_in_editor(request)
        in_place = stay and bool(request.htmx)
        form = NewNoteForm(request.POST, instance=note)
        if form.is_valid():
            note = form.save()
            url = save_passages(request, note, "modifiée", stay=stay)
            if in_place:
                response = toasts_response(request)
                if str(note.date) != str(note_date):
                    # L'adresse de l'éditeur suit la date : note_form.js y va.
                    response["HX-Redirect"] = url
                return response
            return redirect(url)
        if in_place:
            return form_errors_response(request, form)
    else:
        form = NewNoteForm(instance=note)

    return render(request, "note_taking/note_edit.html", {"form": form, "note": note})


@require_GET
def note_suggestions(request):
    """Les notes, pour les liens de l'éditeur (#206) : le fichier à écrire après
    `](` et la date en texte, les plus récentes d'abord ; `?q=` garde celles dont la
    date commence ainsi (`2026-03`)."""
    query = request.GET.get("q", "").strip()
    days = [
        day
        for day in Note.objects.order_by("-date").values_list("date", flat=True)
        if day.isoformat().startswith(query)
    ][:SUGGESTED_NOTES]
    return JsonResponse(
        {
            "results": [
                {
                    "date": day.isoformat(),
                    "reference": f"{day.isoformat()}.qmd",
                    "label": date_text(day, "long"),
                }
                for day in days
            ]
        }
    )


@require_POST
def delete_note(request, note_date):
    """Supprime une note ; la confirmation se fait par popover native (`confirm_button`, #292)."""
    note = get_object_or_404(Note, date=note_date)
    name = note_name(note)
    note.delete()
    messages.success(request, f"{name} est supprimée.")
    return redirect("note_taking:notes_list")
