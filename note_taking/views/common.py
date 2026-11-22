"""Aides partagées par les vues des notes : nom d'une note dans les messages,
avertissements de l'analyse, page suivante, date lue dans l'adresse."""

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


def next_page(note: Note) -> str:
    """Page après l'enregistrement d'une note : la suite proposée par une autre
    app (#239), sinon la note."""
    if note.follow_ups:
        return note.follow_ups[0].url
    return reverse("note_taking:note_detail", args=[note.date])
