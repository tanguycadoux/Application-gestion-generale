"""Retrait suspendu de l'éditeur (#418) : ce que le JavaScript promet (il n'est pas exécuté
par les tests)."""

from pathlib import Path

from django.conf import settings
from django.test import SimpleTestCase

STATIC_DIR = Path(settings.BASE_DIR) / "note_taking" / "static" / "note_taking"


class HangingIndentTests(SimpleTestCase):
    def read(self, name: str) -> str:
        return (STATIC_DIR / name).read_text(encoding="utf-8")

    def test_branche_dans_l_editeur(self):
        self.assertIn("\n            hangingIndent,\n", self.read("editor.js"))

    def test_colonne_du_texte_est_celle_des_listes(self):
        """La même que pour l'imbrication (#417), pas une autre lecture des marqueurs."""
        script = self.read("hanging.js")

        self.assertIn("itemOf(state, line)", script)
        self.assertIn('from "./lists.js"', script)

    def test_marqueur_jamais_seul_sur_sa_ligne(self):
        """Un premier mot trop long se coupe ; la ligne ne revient pas après le tiret."""
        self.assertIn("cm-hanging-prefix", self.read("hanging.js"))
        self.assertRegex(
            self.read("editor.js"), r'"\.cm-hanging-prefix": \{ whiteSpace: "pre" \}'
        )
