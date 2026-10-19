"""Tests des représentations textuelles des modèles."""

from django.test import SimpleTestCase

from core.models import Project, Subject
from note_taking.models import NotePart


class NotePartStrTests(SimpleTestCase):
    def test_avec_sujet(self):
        part = NotePart(project=Project(name="Alpha"), subject=Subject(name="Mesures"))

        self.assertEqual(str(part), "Alpha, Mesures")

    def test_sans_sujet(self):
        part = NotePart(project=Project(name="Alpha"), subject=None)

        self.assertEqual(str(part), "Alpha")


class TextFieldsDefaultTests(SimpleTestCase):
    def test_contenu_vide_par_defaut(self):
        """#48 : chaîne vide plutôt que None."""
        self.assertEqual(NotePart().content, "")
