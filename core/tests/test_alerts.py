"""Tests des règles CSS propres aux popovers natives. Les toasts sont dans
`test_toasts.py` (#293)."""

from django.test import SimpleTestCase

from .stylesheets import components_layer, read_source_css


class AlertStylesheetTests(SimpleTestCase):
    """Les règles propres des popovers ne gardent que les animations et l'ancrage
    (#154) ; elles sont dans la source de la feuille Tailwind (#217)."""

    def test_regles_dans_le_layer_components(self):
        """Hors layer, ces règles l'emporteraient sur toute classe Tailwind."""
        css = components_layer(read_source_css())

        self.assertIn(".confirm-popover:popover-open {", css)

    def test_regles_reduites_aux_animations(self):
        css = components_layer(read_source_css())

        self.assertNotRegex(css, r"\b(?:color|background|border|box-shadow)\s*:")
        self.assertIn("@keyframes fadeIn", css)

    def test_popover_native_ancree_a_son_bouton(self):
        """Sous son bouton par l'ancrage CSS ; sans lui, le navigateur la centre."""
        css = components_layer(read_source_css())

        self.assertIn("@supports (position-area: bottom)", css)
        self.assertIn("position-area: bottom span-left", css)
