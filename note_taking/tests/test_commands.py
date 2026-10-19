"""Tests de la commande reprocess_notes."""

from io import StringIO

from django.core.management import call_command
from django.test import TestCase

from core.models import Project, Tag
from note_taking.models import Note, NotePart
from todolist.models import Todo


class ReprocessNotesTests(TestCase):
    def setUp(self):
        self.note = Note.objects.create(date="2025-11-24", body="# P\n### A\nx")
        # Note part obsolète, comme après une évolution du parseur.
        part = NotePart.objects.create(
            note=self.note,
            project=Project.objects.create(name="Ancien"),
            content="x",
        )
        part.tags.set([Tag.objects.create(name="obsolète")])

    def reprocess(self, *args):
        out, err = StringIO(), StringIO()
        call_command("reprocess_notes", *args, stdout=out, stderr=err)
        return out.getvalue(), err.getvalue()

    def parts(self, note):
        return [
            (p.project.name, list(p.tags.values_list("name", flat=True)), p.content)
            for p in note.parts.all()
        ]

    def test_recalcule_les_note_parts(self):
        out, _ = self.reprocess()

        self.assertEqual(self.parts(self.note), [("P", ["A"], "x")])
        self.assertIn("1 note(s) recalculée(s), 0 erreur(s)", out)

    def test_simulation_n_enregistre_rien(self):
        out, _ = self.reprocess("--dry-run")

        self.assertEqual(self.parts(self.note), [("Ancien", ["obsolète"], "x")])
        self.assertIn("Simulation", out)

    def test_note_en_erreur_n_empeche_pas_les_autres(self):
        broken = Note.objects.create(date="2025-11-25", body="# P\n![a](absente.png)")

        out, err = self.reprocess()

        self.assertIn(f"note du {broken.date}", err)
        self.assertIn("1 note(s) recalculée(s), 1 erreur(s)", out)
        self.assertEqual(self.parts(self.note), [("P", ["A"], "x")])

    def test_todo_existante_non_recreee(self):
        self.note.body = "# P\n## S\n### TODO\n- Tâche"
        self.note.save()
        self.reprocess()
        todo = Todo.objects.get()
        todo.completed = True
        todo.save()

        out, _ = self.reprocess()

        self.assertEqual(Todo.objects.count(), 1)
        self.assertTrue(Todo.objects.get().completed)
        self.assertIn("0 TODO créée(s)", out)
