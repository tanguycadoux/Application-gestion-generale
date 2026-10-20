"""Tests du style des alertes : toasts et popover cohérents avec l'interface (#154).

Le projet n'a pas de lanceur de tests JavaScript : ces tests lisent le script.
"""

import json
import unittest
import re
from pathlib import Path

from django.contrib.staticfiles import finders
from django.test import TestCase

from core.templatetags.ui import BUTTON_VARIANTS

SHAPE = "rounded-xl border border-slate-200 bg-white p-3 shadow-lg"

TOAST_TYPES = {
    "info": ("info", "border-l-blue-700", "text-blue-800", "bg-blue-500"),
    "success": ("check_circle", "border-l-green-700", "text-green-800", "bg-green-500"),
    "warning": ("warning", "border-l-amber-500", "text-amber-800", "bg-amber-400"),
    "error": ("error", "border-l-red-700", "text-red-800", "bg-red-500"),
}


def read_static(name: str) -> str:
    path = finders.find(name)
    assert isinstance(path, str)
    return Path(path).read_text(encoding="utf-8")


class ButtonVariantsForScriptsTests(TestCase):
    def test_classes_des_boutons_transmises_aux_scripts(self):
        html = self.client.get("/").content.decode()

        match = re.search(
            r'<script id="button-variants" type="application/json">(.*?)</script>',
            html,
        )
        assert match is not None
        self.assertEqual(json.loads(match.group(1)), BUTTON_VARIANTS)
        self.assertLess(
            html.index('id="button-variants"'), html.index("core/alert_system.js")
        )


class AlertScriptStyleTests(TestCase):
    def setUp(self):
        self.script = read_static("core/alert_system.js")

    def test_forme_commune(self):
        """Une seule définition, utilisée par le toast et par la popover."""
        self.assertIn(f'const ALERT_SHAPE = "{SHAPE}";', self.script)
        self.assertGreaterEqual(self.script.count("${ALERT_SHAPE}"), 2)

    def test_toasts_par_type(self):
        for toast_type, classes in TOAST_TYPES.items():
            with self.subTest(toast_type=toast_type):
                for value in classes:
                    self.assertIn(f'"{value}"', self.script)
        self.assertIn("border-l-4", self.script)

    def test_boutons_de_la_popover_selon_les_variantes(self):
        self.assertIn('getElementById("button-variants")', self.script)
        self.assertLess(
            self.script.index("variants.ghost"), self.script.index("variants.danger")
        )

    def test_plus_de_modale(self):
        self.assertNotIn("createModal", self.script)
        self.assertNotIn("alert__modal", self.script)


class ToastProgressTests(TestCase):
    """La barre de progression ne dépend pas de la génération des classes Tailwind.

    La version navigateur de Tailwind génère les classes d'un élément ajouté par
    script après coup : une largeur de départ lue sur `w-full` valait 0 (#154).
    """

    @unittest.expectedFailure
    def test_animation_dans_la_feuille_chargee_au_depart(self):
        css = read_static("core/alert_system.css")

        self.assertIn(".alert__toast-progress {", css)
        self.assertIn("@keyframes alert-toast-progress", css)

    @unittest.expectedFailure
    def test_script_ne_donne_que_la_duree(self):
        script = read_static("core/alert_system.js")

        self.assertIn("alert__toast-progress", script)
        self.assertIn("style.animationDuration", script)
        self.assertNotIn("offsetWidth", script)


class AlertStylesheetTests(TestCase):
    def test_feuille_reduite_aux_animations(self):
        css = read_static("core/alert_system.css")

        self.assertNotRegex(css, r"\b(?:color|background|border|box-shadow)\s*:")
        self.assertIn("transition", css)
        self.assertIn("@keyframes", css)
