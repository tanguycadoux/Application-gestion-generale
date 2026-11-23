"""Bilan d'un titre de projet renommé dans une note (#170)."""

from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render

from core.exceptions import AppError

from ..models import Note
from ..project_renaming import CHOICES, apply_choice
from ..renaming import located_projects
from ..services import process_passages
from .common import next_page


def project_rename_review(request, note_date):
    """Pour chaque titre de projet renommé dans la note : tout renommer, seulement
    dans cette note (choix par défaut : c'est ce qui est enregistré), ou ne pas
    renommer. Puis la suite de l'enregistrement (bilan des tâches) ou la note."""
    note = get_object_or_404(Note, date=note_date)
    pending = list(note.pending_project_renames.all())
    if not pending:
        return redirect("note_taking:note_detail", note_date=note.date)

    if request.method == "POST":
        try:
            for item in pending:
                choice = request.POST.get(f"choice-{item.pk}", "here")
                messages.success(
                    request, apply_choice(item, choice if choice in CHOICES else "here")
                )
            process_passages(note)
        except AppError as e:
            messages.error(request, str(e))
            return redirect("note_taking:project_rename_review", note_date=note.date)
        return redirect(next_page(note))

    rows = [
        {
            "pending": item,
            "others": len(
                {found.note.pk for found in located_projects(item.old_name)} - {note.pk}
            ),
        }
        for item in pending
    ]
    return render(
        request, "note_taking/project_rename_review.html", {"note": note, "rows": rows}
    )
