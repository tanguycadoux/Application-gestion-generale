"""Tests du style des éléments communs en classes Tailwind (#79)."""

import unittest

from django.contrib.staticfiles import finders
from django.test import TestCase


def read_static(name: str) -> str:
    path = finders.find(name)
    assert isinstance(path, str)
    with open(path, encoding="utf-8") as file:
        return file.read()


class CoreStyleTests(TestCase):
    def test_panneau_admin_en_classes_tailwind(self):
        html = self.client.get("/").content.decode()

        self.assertNotIn("admin-side-panel", html)
        self.assertIn("bg-neutral-95", html)

    @unittest.expectedFailure
    def test_plus_de_feuille_de_style_commune(self):
        """Tout le style commun est en Tailwind : core/style.css n'existe plus."""
        html = self.client.get("/").content.decode()

        self.assertIsNone(finders.find("core/style.css"))
        self.assertNotIn("core/style.css", html)

    def test_alertes_dans_le_layer_components(self):
        """Hors layer, ces règles l'emporteraient sur toute classe Tailwind."""
        css = read_static("core/alert_system.css")

        self.assertTrue(css.lstrip().startswith("@layer components {"))

    def test_titre_de_l_accueil(self):
        response = self.client.get("/")

        self.assertContains(response, "<title>Gestion générale</title>", html=True)
