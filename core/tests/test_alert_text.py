"""Tests des alertes : les textes s'affichent tels quels, sans être lus comme du HTML (#142).

Le projet n'a pas de lanceur de tests JavaScript : ces tests lisent le script.
"""

import re
from pathlib import Path

from django.contrib.staticfiles import finders
from django.test import SimpleTestCase


def read_script() -> str:
    path = finders.find("core/alert_system.js")
    assert isinstance(path, str)
    return Path(path).read_text(encoding="utf-8")


class AlertTextTests(SimpleTestCase):
    def setUp(self):
        self.script = read_script()

    def test_pas_d_insertion_en_html(self):
        self.assertNotIn("innerHTML", self.script)
        self.assertNotIn("insertAdjacentHTML", self.script)

    def test_textes_places_en_texte(self):
        self.assertIn("textContent", self.script)

    def test_pas_de_texte_dans_un_gabarit_de_chaine(self):
        """Message, titre et libellés ne passent plus par une chaîne `${…}` en HTML."""
        interpolations = re.findall(r"\$\{([^}]*)\}", self.script)

        for name in ("message", "display_title", "button_data.message"):
            with self.subTest(name=name):
                self.assertNotIn(name, [i.strip() for i in interpolations])
