"""Cycle de vie des tâches issues des notes (#240).

Une tâche générée est identifiée par la date de la note, le chemin des titres
tels qu'écrits (sans `TODO`) et le chemin de sa ligne.
"""

from django.test import TestCase

from core.models import Project
from note_taking.models import Note
from note_taking.services import process_note_parts
from todolist.models import Todo


class LifecycleTestCase(TestCase):
    def save_note(self, body: str, date: str = "2025-11-24") -> Note:
        note, _ = Note.objects.update_or_create(date=date, defaults={"body": body})
        process_note_parts(note)
        return note

    def titles(self) -> list[str]:
        return list(Todo.objects.order_by("pk").values_list("title", flat=True))


class IdentityTests(LifecycleTestCase):
    def test_meme_ligne_sous_deux_sujets(self):
        self.save_note("# P\n## A\n### TODO\n- Tâche\n## B\n### TODO\n- Tâche")

        self.assertEqual(self.titles(), ["Tâche", "Tâche"])

    def test_meme_ligne_sous_deux_parents(self):
        self.save_note("# P\n### TODO\n- A\n  - Relire\n- B\n  - Relire")

        relire = Todo.objects.filter(title="Relire").select_related("parent")
        self.assertEqual(sorted(todo.parent.title for todo in relire), ["A", "B"])

    def test_chemin_retenu(self):
        self.save_note("# P\n## S\n### TODO\n- A\n  - B")

        self.assertEqual(Todo.objects.get(title="B").note_path, "P › S › A")

    def test_reenregistree_sans_doublon(self):
        body = "# P\n## A\n### TODO\n- Tâche\n  - Sous-tâche"
        self.save_note(body)
        self.save_note(body)

        self.assertEqual(self.titles(), ["Tâche", "Sous-tâche"])

    def test_tache_d_avant_reprise_sans_doublon(self):
        """Une tâche créée avant #240, sans chemin, est reprise par sa ligne."""
        Todo.objects.create(
            title="Renommée",
            project=Project.objects.create(name="P"),
            created_from_note=True,
            note_part_date="2025-11-24",
            note_part_text="Tâche",
        )

        self.save_note("# P\n## A\n### TODO\n- Tâche")

        todo = Todo.objects.get()
        self.assertEqual((todo.title, todo.note_path), ("Renommée", "P › A"))
