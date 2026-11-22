"""Tests des représentations textuelles des modèles."""

from django.test import SimpleTestCase

from core.models import Project, Section
from note_taking.models import Passage


class PassageStrTests(SimpleTestCase):
    def test_avec_sujet(self):
        part = Passage(project=Project(name="Alpha"), section=Section(name="Mesures"))

        self.assertEqual(str(part), "Alpha, Mesures")

    def test_sans_sujet(self):
        part = Passage(project=Project(name="Alpha"), section=None)

        self.assertEqual(str(part), "Alpha")


class TextFieldsDefaultTests(SimpleTestCase):
    def test_contenu_vide_par_defaut(self):
        """#48 : chaîne vide plutôt que None."""
        self.assertEqual(Passage().content, "")
