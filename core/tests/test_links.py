"""Tests du style des liens : un style de base commun aux liens de texte (#127)."""

import re
from pathlib import Path

from django.conf import settings
from django.test import TestCase

APPS = ("core", "images", "note_taking", "todolist")

# Lien qui porte lui-même un style de lien de texte (couleur, soulignement).
STYLED_LINK_REGEX = re.compile(
    r'<a\s[^>]*class="[^"]*\b(?:underline|text-blue-\d+)\b[^"]*"', re.DOTALL
)


def templates() -> list[Path]:
    return [
        path
        for app in APPS
        for path in (Path(settings.BASE_DIR) / app).glob("**/templates/**/*.html")
    ]


class LinkStyleTests(TestCase):
    def setUp(self):
        self.html = self.client.get("/").content.decode()

    def test_style_de_base_des_liens_de_texte(self):
        self.assertIn("a:not([class]) {", self.html)
        self.assertIn(
            "@apply text-blue-700 underline underline-offset-2"
            " hover:text-blue-900 hover:decoration-2",
            self.html,
        )

    def test_focus_visible_des_liens(self):
        self.assertIn(
            "@apply rounded-sm outline-2 outline-offset-2 outline-blue-700",
            self.html,
        )

    def test_gabarits_trouves(self):
        self.assertGreater(len(templates()), 20)

    def test_pas_de_style_de_lien_propre_dans_les_gabarits(self):
        for path in templates():
            with self.subTest(path=str(path)):
                html = path.read_text(encoding="utf-8")
                self.assertEqual(STYLED_LINK_REGEX.findall(html), [])
