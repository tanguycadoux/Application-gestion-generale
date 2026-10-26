"""Signaux de la prise de notes, écoutés par les apps qui en dépendent."""

from dataclasses import dataclass

from django.dispatch import Signal

# Envoyé après le recalcul des note parts d'une note, dans la même transaction,
# avec `note` et `note_parts`. Les tâches issues des notes en découlent (todolist).
# Un receveur peut renvoyer un `NoteFollowUp`.
note_parts_processed = Signal()


@dataclass
class NoteFollowUp:
    """Suite à donner à l'enregistrement d'une note, proposée par une autre app
    (#239) : « 2 tâches créées » et la page qui les présente.

    La note ne connaît pas cette app : elle redirige vers `url` après le
    formulaire, ou cite `label` et `url` dans le compte rendu d'import.
    """

    label: str
    url: str
