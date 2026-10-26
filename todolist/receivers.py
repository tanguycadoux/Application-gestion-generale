"""Tâches créées depuis les notes, à l'écoute de la prise de notes."""

from django.dispatch import receiver
from django.urls import reverse

from note_taking.signals import NoteFollowUp, note_parts_processed

from .services import create_todos_from_note_part


@receiver(note_parts_processed)
def create_todos_from_note_parts(
    sender, note, note_parts, **kwargs
) -> NoteFollowUp | None:
    """Crée les tâches des note parts ; s'il y en a de nouvelles, propose leur
    bilan (#239)."""
    created = [
        todo
        for note_part in note_parts
        for todo in create_todos_from_note_part(note_part)
    ]
    if not created:
        return None
    label = "1 tâche créée" if len(created) == 1 else f"{len(created)} tâches créées"
    ids = ",".join(str(todo.pk) for todo in created)
    url = reverse("todolist:note_review", args=[str(note.date)])
    return NoteFollowUp(label, f"{url}?ids={ids}")
