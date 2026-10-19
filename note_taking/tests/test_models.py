"""Tests des représentations textuelles des modèles."""

from django.test import SimpleTestCase

from note_taking.models import NotePart, Project


class NotePartStrTests(SimpleTestCase):
    def test_avec_sujet(self):
        part = NotePart(project=Project(name="Alpha"), subject="Mesures")

        self.assertEqual(str(part), "Alpha, Mesures")

    def test_sans_sujet(self):
        part = NotePart(project=Project(name="Alpha"), subject=None)

        self.assertEqual(str(part), "Alpha")
