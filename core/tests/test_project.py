"""Tests du modèle Project partagé entre notes et TODO."""

from django.db.models import ProtectedError
from django.test import TestCase

from note_taking.models import Note
from note_taking.services import process_note_parts
from todolist.models import Todo


class ProjectDeletionTests(TestCase):
    """Un projet utilisé ne peut pas être supprimé (#19)."""

    def setUp(self):
        self.note = Note.objects.create(
            date="2025-11-24", body="# P\n## S\n::: {.metadata}\ntodo: true\n:::\n- a"
        )
        process_note_parts(self.note)

    def test_projet_utilise_par_une_note_part(self):
        project = self.note.parts.get().project
        Todo.objects.all().delete()

        with self.assertRaises(ProtectedError):
            project.delete()

    def test_projet_utilise_par_une_todo(self):
        project = Todo.objects.get().project
        self.note.delete()

        with self.assertRaises(ProtectedError):
            project.delete()
        self.assertTrue(Todo.objects.exists())
