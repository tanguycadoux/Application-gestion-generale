"""Pages des notes : accueil, tableau, note, création, édition, suppression,
et les anciennes adresses par id (#273)."""

import copy
import logging
from urllib.parse import quote

from django.contrib import messages
from django.db.models import Prefetch
from django.http import Http404, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET, require_POST
from django.views.generic import DetailView, ListView

from core.dates import date_text, parse_date_param
from core.exceptions import AppError

from .. import note_table
from ..edit_conflict import conflict_reason
from ..forms import NewNoteForm
from ..models import Note, Passage
from ..note_calendar import requested_month_calendar
from ..note_citations import citations
from ..note_outline import outline_sections
from ..pending_renames import add_pending_follow_up
from ..project_renaming import record_project_renames
from ..rendering import render_note_body
from ..services import process_passages
from .common import next_page, note_name, save_warnings

logger = logging.getLogger(__name__)

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
        context["projects"] = self.object.projects
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
        # Un titre de projet renommé attend un choix (#170).
        add_pending_follow_up(note)
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


def note_version(note: Note) -> str:
    """Ce que l'éditeur renvoie pour dire quelle version de la note il a ouverte
    (#386) : sa date de modification, relue en base."""
    updated = Note.objects.values_list("updated", flat=True).get(pk=note.pk)
    return updated.isoformat()


def changed_since_opened(request, note: Note) -> bool:
    """La note a changé depuis l'ouverture de l'éditeur (capture rapide, niveau
    renommé, autre onglet), et remplacer **cette** version n'a pas été demandé."""
    opened = request.POST.get("version")
    if not opened:
        return False
    return note_version(note) not in (opened, request.POST.get("overwrite"))


def conflict_response(request, note: Note, in_place: bool) -> HttpResponse:
    """Rien n'est enregistré : l'éditeur garde le texte saisi et propose de voir la
    version enregistrée, ou de la remplacer. La raison est dite, et tracée (#468)."""
    # Relue : la note a pu changer depuis le début de la requête.
    note.refresh_from_db()
    current = note.updated.isoformat()
    reason = conflict_reason(note, request.POST["version"])
    logger.warning(
        "Note %s, conflit : ouverte=%s enregistrée=%s overwrite=%s "
        "dernière modification : source=%s",
        note.date,
        request.POST["version"],
        current,
        request.POST.get("overwrite") or "non",
        note.updated_by or "inconnue",
    )
    if in_place:
        messages.error(
            request,
            "La note n'est pas enregistrée : elle a changé depuis l'ouverture de "
            "l'éditeur.",
        )
        response = toasts_response(request, status=409)
        response["X-Note-Version"] = current
        # Encodé : un en-tête ne porte pas d'accents.
        response["X-Note-Conflict"] = quote(reason)
        return response
    return render(
        request,
        "note_taking/note_edit.html",
        {
            # Une copie : la validation écrit le texte saisi dans l'instance.
            "form": NewNoteForm(request.POST, instance=copy.copy(note)),
            "note": note,
            "version": request.POST["version"],
            "current_version": current,
            "conflict": True,
            "conflict_reason": reason,
        },
        status=409,
    )


# Jamais reprise du cache (#468) : revenir à l'éditeur par Précédent redemande la page,
# avec le texte et la version à jour.
@never_cache
def new_note(request):
    if request.method == "POST":
        form = NewNoteForm(request.POST)
        if form.is_valid():
            note = form.save(commit=False)
            note.save(source=Note.Source.EDITOR)
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


@never_cache
def edit_note(request, note_date):
    note = get_object_or_404(Note, date=note_date)

    if request.method == "POST":
        stay = stays_in_editor(request)
        in_place = stay and bool(request.htmx)
        if changed_since_opened(request, note):
            return conflict_response(request, note, in_place)
        version = note_version(note)
        old_body = note.body
        form = NewNoteForm(request.POST, instance=note)
        if form.is_valid():
            note = form.save(commit=False)
            overwriting = request.POST.get("overwrite") == version
            note.save(
                source=Note.Source.OVERWRITE if overwriting else Note.Source.EDITOR
            )
            # Un titre de projet renommé : en attente du choix, tâches qui suivent (#170).
            record_project_renames(note, old_body, note.body)
            url = save_passages(request, note, "modifiée", stay=stay)
            if in_place:
                response = toasts_response(request)
                response["X-Note-Version"] = note_version(note)
                if str(note.date) != str(note_date):
                    # L'adresse de l'éditeur suit la date : note_form.js y va.
                    response["HX-Redirect"] = url
                return response
            return redirect(url)
        if in_place:
            return form_errors_response(request, form)
    else:
        version = note_version(note)
        form = NewNoteForm(instance=note)

    return render(
        request,
        "note_taking/note_edit.html",
        {"form": form, "note": note, "version": version},
    )


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
                    # Sans extension : l'export l'ajoute pour Quarto (#206).
                    "reference": day.isoformat(),
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
