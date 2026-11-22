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

    def test_niveaux_de_titres_distincts(self):
        """Chaque niveau de titre a sa taille, ou sa couleur et sa casse (#381)."""
        css = self.read("note_taking/style.css")

        for rule in (
            ".rendered-content h2 {\n    font-size: 1.5rem;",
            ".rendered-content h3 { font-size: 1.25rem;",
            ".rendered-content h4 { font-size: 1.125rem;",
            "color: var(--color-slate-700); }",
            "text-transform: uppercase;",
        ):
            self.assertIn(rule, css)

    def test_titre_de_projet_souligne_d_un_filet(self):
        css = self.read("note_taking/style.css")

        self.assertIn("border-bottom: 1px solid var(--color-slate-200);", css)
