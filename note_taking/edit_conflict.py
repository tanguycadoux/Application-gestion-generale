"""Conflit d'enregistrement expliqué (#468) : ce qui a modifié la note, et quand."""

import datetime

from django.utils import timezone

from core.dates import date_text, local

from .models import Note


def read_version(version: str) -> datetime.datetime | None:
    """Date de modification portée par une version, rien si elle est illisible."""
    try:
        read = datetime.datetime.fromisoformat(version)
    except ValueError:
        return None
    return read if timezone.is_aware(read) else None


def moment(value: datetime.datetime, preposition: str, clock: str) -> str:
    """« à 09:12 », ou « le 5 mars 2026 à 09:12 » si ce n'est pas aujourd'hui."""
    value = local(value)
    time = value.strftime(clock)
    if value.date() == timezone.localdate():
        return f"{preposition} {time}"
    day = date_text(value, "moyen")
    return f"le {day} à {time}" if preposition == "à" else f"du {day} à {time}"


def conflict_reason(note: Note, opened_version: str) -> str:
    """Phrase de l'encadré : la dernière modification de la note, et la version dont
    part l'éditeur."""
    opened = read_version(opened_version)
    if opened is None or opened >= note.updated:
        return (
            "La version ouverte par l'éditeur n'est pas celle de la note, mais aucune "
            "modification connue ne l'explique : le fichier de log aidera à comprendre."
        )
    # Dans la même minute, les secondes distinguent les deux versions.
    same_minute = f"{opened:%F %H:%M}" == f"{note.updated:%F %H:%M}"
    clock = "%H:%M:%S" if same_minute else "%H:%M"
    # Un enregistrement de l'éditeur : celui d'un autre onglet, ou de celui-ci si la
    # page a été reprise du cache.
    by = {
        "": ", sans que l'application sache par quoi",
        Note.Source.EDITOR: " par l'éditeur (dans cet onglet ou un autre)",
    }.get(note.updated_by, f" par {note.source_label}")
    return (
        f"La note a été modifiée {moment(note.updated, 'à', clock)}{by}. "
        f"L'éditeur était ouvert sur la version {moment(opened, 'de', clock)}."
    )
