"""Regrouper les titres répétés d'une note (#315) : l'aperçu, puis l'écriture."""

from django.contrib import messages
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render

from core.exceptions import AppError

from ..models import Note
from ..qmd.regroup import RepeatedHeading, regroup_headings, repeated_headings
from ..services import process_passages
from .common import next_page, note_name


def proposed(headings: list[RepeatedHeading]) -> list[RepeatedHeading]:
    return [heading for heading in headings if not heading.blocked]


def repeated_message(headings: list[RepeatedHeading]) -> str:
    """Ce que dit l'enregistrement d'une note dont des titres se répètent."""
    titles = ", ".join(f"« {heading.title} »" for heading in headings[:3])
    more = "…" if len(headings) > 3 else ""
    return (
        f"Titres écrits plusieurs fois ({titles}{more}) : leur regroupement est "
        "proposé sur la page de la note."
    )


def regroup_review(request, note_date):
    """Les titres répétés de la note, chacun avec une case cochée : les cochés
    sont regroupés, la note est réécrite puis recalculée. Rien n'est écrit si la
    note a changé depuis l'aperçu."""
    note = get_object_or_404(Note, date=note_date)
    version = note.updated.isoformat()

    if request.method == "POST":
        keys = set(request.POST.getlist("headings"))
        if request.POST.get("version") != version:
            messages.error(
                request,
                "La note a changé depuis l'aperçu : rien n'a été modifié. Revoir "
                "l'aperçu ci-dessous.",
            )
            return redirect("note_taking:regroup_review", note_date=note.date)
        if not keys:
            messages.info(request, "Aucun titre choisi : la note est inchangée.")
            return redirect("note_taking:note_detail", note_date=note.date)
        try:
            with transaction.atomic():
                note.body = regroup_headings(note.body, keys)
                note.save(source=Note.Source.REGROUP)
                process_passages(note)
        except AppError as e:
            messages.error(request, str(e))
            return redirect("note_taking:regroup_review", note_date=note.date)
        count = len(keys)
        plural = "s" if count > 1 else ""
        messages.success(
            request,
            f"{note_name(note)} : {count} titre{plural} regroupé{plural}.",
        )
        return redirect(next_page(note))

    headings = repeated_headings(note.body)
    if not headings:
        messages.info(request, "Aucun titre n'est répété dans cette note.")
        return redirect("note_taking:note_detail", note_date=note.date)
    preview_keys = {heading.key for heading in proposed(headings)}
    try:
        preview = regroup_headings(note.body, preview_keys) if preview_keys else ""
    except AppError:
        # Chacun est sûr seul, pas tous ensemble : pas d'aperçu d'ensemble.
        preview = ""
    return render(
        request,
        "note_taking/regroup_review.html",
        {
            "note": note,
            "version": version,
            "headings": headings,
            "proposed": len(preview_keys),
            "preview": preview,
        },
    )
