"""Signaux de la prise de notes, écoutés par les apps qui en dépendent."""

from django.dispatch import Signal

# Envoyé après le recalcul des note parts d'une note, dans la même transaction,
# avec `note` et `note_parts`. Les tâches issues des notes en découlent (todolist).
note_parts_processed = Signal()
