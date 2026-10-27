"""Tests de la popover de colonne (`createPopoverBase`, `alert_system.js`) et des
règles CSS propres aux alertes. Les toasts sont dans `test_toasts.py` (#293).

Le projet n'a pas de lanceur de tests JavaScript : les tests du script le lisent.
"""

from pathlib import Path

from django.contrib.staticfiles import finders
from django.test import SimpleTestCase

from .stylesheets import components_layer, read_source_css

SHAPE = "rounded-xl border border-slate-200 bg-white p-3 shadow-lg"


def read_static(name: str) -> str:
    path = finders.find(name)
    assert isinstance(path, str)
    return Path(path).read_text(encoding="utf-8")


class PopoverScriptTests(SimpleTestCase):
    def setUp(self):
        self.script = read_static("core/alert_system.js")

    def test_textes_places_en_texte_sans_html(self):
        """Les textes s'affichent tels quels, sans être lus comme du HTML (#142)."""
        self.assertIn("textContent", self.script)
        self.assertNotIn("innerHTML", self.script)
        self.assertNotIn("insertAdjacentHTML", self.script)

    def test_forme_de_la_popover(self):
        self.assertIn(f'const ALERT_SHAPE = "{SHAPE}";', self.script)
        self.assertIn("${ALERT_SHAPE}", self.script)

    def test_plus_de_toast_ni_de_confirmation_en_javascript(self):
        self.assertNotIn("toast", self.script.lower())
        self.assertNotIn("confirmAt", self.script)


class AlertStylesheetTests(SimpleTestCase):
    """Les règles propres des alertes ne gardent que les animations (#154) ; elles
    sont dans la source de la feuille Tailwind (#217)."""

    def test_regles_dans_le_layer_components(self):
        """Hors layer, ces règles l'emporteraient sur toute classe Tailwind."""
        css = components_layer(read_source_css())

        self.assertIn(".alert__popover {", css)
        self.assertIn(".confirm-popover:popover-open {", css)

    def test_regles_reduites_aux_animations(self):
        css = components_layer(read_source_css())

        self.assertNotRegex(css, r"\b(?:color|background|border|box-shadow)\s*:")
        self.assertIn("@keyframes fadeIn", css)

    def test_plus_de_regle_de_toast(self):
        """Le toast est du HTML rendu par le serveur, en classes Tailwind (#293)."""
        css = read_source_css()

        self.assertNotIn("alert__toast", css)
        self.assertNotIn("alert-toast-progress", css)

    def test_popover_native_ancree_a_son_bouton(self):
        """Sous son bouton par l'ancrage CSS ; sans lui, le navigateur la centre."""
        css = components_layer(read_source_css())

        self.assertIn("@supports (position-area: bottom)", css)
        self.assertIn("position-area: bottom span-left", css)
