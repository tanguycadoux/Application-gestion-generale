"""Capture rapide (#386) : une ligne ajoutée à la note du jour depuis n'importe quelle
page, sans la quitter."""

from django.contrib import messages
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.html import format_html
from django.views.decorators.http import require_http_methods

from core.exceptions import AppError

from ..models import Note
from ..quick_capture import capture, targets
from .common import save_warnings
from .notes import toasts_response


@require_http_methods(["GET", "POST"])
def quick_capture(request):
    """GET : le plan de la note du jour, pour le dialogue ; sans JavaScript (une
    navigation), le formulaire de la note du jour. POST : l'ajout, dont le compte
    rendu est en toasts, sans redirection vers le bilan des tâches."""
    if request.method == "POST":
        return add_capture(request)
    today = timezone.localdate()
    note = Note.objects.filter(date=today).first()
    if request.htmx:
        return render(
            request,
            "note_taking/quick_capture_plan.html",
            {
                "today": today,
                "note": note,
                "targets": targets(note.body if note else ""),
            },
        )
    if note:
        return redirect("note_taking:edit_note", note_date=today)
    return redirect(f"{reverse('note_taking:new_note')}?date={today.isoformat()}")


def add_capture(request):
    is_task = bool(request.POST.get("is_task"))
    new_title = request.POST.get("new_title", "")
    try:
        note = capture(
            request.POST.get("text", ""),
            key=request.POST.get("target", ""),
            is_task=is_task,
            new_title=new_title,
        )
    except AppError as e:
        messages.error(request, f"Rien n'est ajouté : {e}")
        return toasts_response(request, status=422)

    message = format_html(
        'Ajouté à la <a href="{}">note du jour</a>.',
        reverse("note_taking:note_detail", args=[note.date]),
    )
    if is_task:
        for follow_up in note.follow_ups:
            message += format_html(
                ' <a href="{}">{}</a>.', follow_up.url, follow_up.label
            )
    messages.success(request, message)
    # Le texte sans projet est le choix par défaut : le rappeler à chaque capture
    # serait du bruit (« À traiter » le fait, #384). Un nouveau titre, lui, peut être
    # proche d'un titre existant (#374).
    if new_title.strip():
        save_warnings(request, note)
    return toasts_response(request)
