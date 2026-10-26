"""Tâches créées depuis les notes, à l'écoute de la prise de notes."""

from django.dispatch import receiver

from note_taking.signals import note_parts_processed

from .services import create_todos_from_note_part


@receiver(note_parts_processed)
def create_todos_from_note_parts(sender, note_parts, **kwargs):
    for note_part in note_parts:
        create_todos_from_note_part(note_part)
