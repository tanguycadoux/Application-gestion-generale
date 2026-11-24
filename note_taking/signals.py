"""Signaux de la prise de notes, écoutés par les apps qui en dépendent."""

from dataclasses import dataclass
from typing import TYPE_CHECKING

from django.dispatch import Signal

# Les modèles importent ce module.
if TYPE_CHECKING:
    from .models import Note

# Envoyé après le recalcul des passages d'une note, dans la même transaction,
# avec `note` et `passages`. Les tâches issues des notes en découlent (todolist).
# Un receveur peut renvoyer un `NoteFollowUp`.
passages_processed = Signal()

# Envoyé quand le renommage d'un niveau de chemin réécrit des titres d'une note
# (#299), juste avant le recalcul de ses passages, avec `note`, `old_body` et
# `new_body`. Les tâches issues des notes suivent leurs titres (todolist).
note_headings_renamed = Signal()


# Envoyé pour le bilan d'un renommage de niveau (#376), avec `sections` : la liste des
# `ReviewedSection` dont les titres seraient réécrits. Un receveur renvoie, pour
# chacune et dans le même ordre, les titres des tâches qui y sont écrites.
sections_reviewed = Signal()


@dataclass(frozen=True)
class ReviewedSection:
    """Une section d'une note, sous-titres compris : ses lignes, à partir de 1."""

    note: Note
    start_line: int
    end_line: int


@dataclass
class NoteFollowUp:
    """Suite à donner à l'enregistrement d'une note, proposée par une autre app
    (#239) : « 2 tâches créées » et la page qui les présente.

    La note ne connaît pas cette app : elle redirige vers `url` après le
    formulaire, ou cite `label` et `url` dans le compte rendu d'import.
    """

    label: str
    url: str
