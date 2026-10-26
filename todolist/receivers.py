"""Tâches créées depuis les notes, à l'écoute de la prise de notes."""

from django.dispatch import receiver
from django.urls import reverse

from note_taking.signals import NoteFollowUp, note_parts_processed

from .services import (
    create_todos_from_note_part,
    mark_gone_lines,
    note_lines,
    note_todos_to_review,
)


@receiver(note_parts_processed)
def create_todos_from_note_parts(
    sender, note, note_parts, **kwargs
) -> NoteFollowUp | None:
    """Crée les tâches des note parts et repère celles dont la ligne a disparu ;
    s'il en reste à revoir, propose le bilan de la note (#239, #240)."""
    for note_part in note_parts:
        create_todos_from_note_part(note_part)
    mark_gone_lines(note.date, note_lines(note_parts))

    count = note_todos_to_review(note.date).count()
    if not count:
        return None
    label = "1 tâche à revoir" if count == 1 else f"{count} tâches à revoir"
    return NoteFollowUp(label, reverse("todolist:note_review", args=[str(note.date)]))
