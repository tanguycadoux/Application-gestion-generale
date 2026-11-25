"""Retrait suspendu de l'éditeur (#418) : ce que le JavaScript promet (il n'est pas exécuté
par les tests)."""

from pathlib import Path
from unittest import expectedFailure

from django.conf import settings
from django.test import SimpleTestCase

STATIC_DIR = Path(settings.BASE_DIR) / "note_taking" / "static" / "note_taking"


class HangingIndentTests(SimpleTestCase):
    def read(self, name: str) -> str:
        return (STATIC_DIR / name).read_text(encoding="utf-8")

    @expectedFailure
    def test_branche_dans_l_editeur(self):
        self.assertIn("\n                hangingIndent,\n", self.read("editor.js"))

    @expectedFailure
    def test_colonne_du_texte_est_celle_des_listes(self):
        """La même que pour l'imbrication (#417), pas une autre lecture des marqueurs."""
        script = self.read("hanging.js")

        self.assertIn("itemOf(state, line)", script)
        self.assertIn('from "./lists.js"', script)
