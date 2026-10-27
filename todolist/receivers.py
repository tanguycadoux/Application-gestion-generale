"""Tâches créées depuis les notes, à l'écoute de la prise de notes."""

from django.dispatch import receiver
from django.urls import reverse

from note_taking.signals import (
    NoteFollowUp,
    note_headings_renamed,
    note_parts_processed,
)

from .models import Todo
from .services import (
    create_todos_from_note_part,
    mark_gone_lines,
    move_tasks,
    note_lines,
    note_todos_to_review,
    renamed_identities,
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


@receiver(note_headings_renamed)
def follow_renamed_headings(sender, note, old_body, new_body, **kwargs) -> None:
    """Les tâches issues d'une note suivent ses titres réécrits : leur chemin de
    ligne change, pas leur fiche (#299). Une note sans tâche n'a rien à suivre."""
    if not Todo.all_objects.filter(
        created_from_note=True, note_part_date=note.date
    ).exists():
        return
    move_tasks(note.date, renamed_identities(note.date, old_body, new_body))
