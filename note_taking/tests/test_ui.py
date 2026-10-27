"""Tests du tableau des notes et des feuilles de note_taking."""

from django.contrib.staticfiles import finders
from django.test import TestCase


class StylesheetsTests(TestCase):
    def read(self, name: str) -> str:
        path = finders.find(name)
        assert isinstance(path, str)
        with open(path, encoding="utf-8") as file:
            return file.read()

    def test_tableaux_du_contenu_rendu_encadres(self):
        css = self.read("note_taking/style.css")

        self.assertIn(".rendered-content table", css)
