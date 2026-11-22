"""Import et export : fichiers importés, source d'une note remplacée, archives
zip d'une note ou de toutes."""

import tempfile
from functools import partial

from django.contrib import messages
from django.http import FileResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from core.exceptions import AppError

from .. import importing
from ..models import Note
from ..qmd.export import write_note_archive, write_notes_archive
from ..services import update_note_from_source_file
from .common import next_page, note_name, warnings_message


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
