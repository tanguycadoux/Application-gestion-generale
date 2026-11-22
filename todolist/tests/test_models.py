"""Tests du modèle Task."""

from django.test import SimpleTestCase

from todolist.models import Task


class TodoDefaultsTests(SimpleTestCase):
    def test_texte_de_note_vide_par_defaut(self):
        """#48 : chaîne vide plutôt que None pour une TODO créée à la main."""
        self.assertEqual(Task(title="Tâche").note_part_text, "")
