"""Tâches issues des notes : titre retenu pour chaque ligne (#222)."""

from django.test import TestCase

from note_taking.models import Note
from note_taking.services import process_note_parts
from todolist.forms import TodoForm
from todolist.models import Todo


class NoteTodoTitleTests(TestCase):
    def titles(self, *lines: str) -> list[str]:
        body = "# P\n::: {.metadata}\ntodo: true\n:::\n" + "\n".join(lines)
        note = Note.objects.create(date="2025-11-24", body=body)
        process_note_parts(note)
        return list(Todo.objects.order_by("pk").values_list("title", flat=True))

    def test_marqueurs_de_liste_retires(self):
        self.assertEqual(
            self.titles(
                "- tiret",
                "* étoile",
                "+ plus",
                "1. numérotée",
                "2) numérotée aussi",
                "  - sous-liste",
            ),
            [
                "tiret",
                "étoile",
                "plus",
                "numérotée",
                "numérotée aussi",
                "sous-liste",
            ],
        )

    def test_case_cochee_ignoree(self):
        """Décision du 2026-10-27 : `[x]` ne crée pas de tâche, terminée ou non."""
        self.assertEqual(
            self.titles("- [ ] à faire", "- [x] cochée", "* [X] majuscule"),
            ["à faire"],
        )
        self.assertFalse(Todo.objects.filter(done=True).exists())

    def test_ligne_sans_marqueur_ignoree(self):
        """Seuls les éléments de liste sont des tâches ; un tiret dans le texte
        reste dans le titre."""
        self.assertEqual(
            self.titles("Relire - corriger", "- Pièce 3-4"),
            ["Pièce 3-4"],
        )

    def test_marqueur_seul_ignore(self):
        self.assertEqual(self.titles("-", "*", "1.", "- [ ]", "- Tâche"), ["Tâche"])

    def test_ligne_longue_modifiable(self):
        """Une tâche de 300 caractères s'enregistre à nouveau sans modification."""
        line = "Tâche " + "x" * 294
        self.titles("- " + line)
        todo = Todo.objects.get()

        form = TodoForm(
            data={
                "title": todo.title,
                "project": todo.project.pk,
                "priority": todo.priority,
                "progress": todo.progress,
            },
            instance=todo,
        )

        self.assertEqual(todo.title, line)
        self.assertTrue(form.is_valid(), form.errors)
