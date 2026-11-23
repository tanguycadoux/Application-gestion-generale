"""Aides partagées par les vues des notes : nom d'une note dans les messages,
avertissements de l'analyse et liens vers des notes absentes, page suivante, date
lue dans l'adresse."""

from datetime import date

from django.contrib import messages
from django.urls import reverse

from core.dates import date_text

from ..models import Note


def note_name(note: Note) -> str:
    """« La note du 24 novembre 2025 », pour les messages."""
    return f"La note du {date_text(note.date, 'moyen')}"


def warnings_message(warnings: tuple[str, ...]) -> str:
    """Le premier avertissement de l'analyse d'une note (titre qui saute un niveau,
    #305), puis le nombre des autres : les lister tous noierait le toast."""
    others = len(warnings) - 1
    if not others:
        return warnings[0]
    plural = "s" if others > 1 else ""
    return f"{warnings[0]} {others} autre{plural} titre{plural} à vérifier."


def missing_links_message(days: tuple[date, ...]) -> str:
    """Les notes absentes que la note cite (#206) : le lien est gardé et signalé."""
    listed = ", ".join(date_text(day, "moyen") for day in days)
    if len(days) == 1:
        return (
            f"Lien vers une note absente ({listed}) : signalé dans la page, il mènera "
            "à la note une fois créée."
        )
    return (
        f"Liens vers des notes absentes ({listed}) : signalés dans la page, ils "
        "mèneront aux notes une fois créées."
    )


def save_warnings(request, note: Note) -> None:
    """Les avertissements d'un enregistrement réussi, en toasts : ceux de l'analyse,
    puis les liens vers des notes absentes."""
    if note.warnings:
        messages.warning(request, warnings_message(note.warnings))
    if note.missing_links:
        messages.warning(request, missing_links_message(note.missing_links))


def next_page(note: Note) -> str:
    """Page après l'enregistrement d'une note : la suite proposée par une autre
    app (#239), sinon la note."""
    if note.follow_ups:
        return note.follow_ups[0].url
    return reverse("note_taking:note_detail", args=[note.date])
