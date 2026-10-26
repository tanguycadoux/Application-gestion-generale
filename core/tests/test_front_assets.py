"""Tailwind compilé et htmx servis en local, sans CDN (#217)."""

import re
from pathlib import Path

from django.conf import settings
from django.contrib.staticfiles import finders
from django.test import TestCase
from django.urls import reverse

SOURCE_CSS = Path(settings.BASE_DIR) / "assets" / "css" / "source.css"

# Une page par gabarit de base d'app.
PAGES = ("core:index", "core:projects", "note_taking:index", "todolist:index")

SCRIPT_SRC_REGEX = re.compile(r"<script[^>]*\bsrc=\"(?P<src>[^\"]+)\"")


class FrontAssetsTests(TestCase):
    def pages(self) -> dict[str, str]:
        return {name: self.client.get(reverse(name)).content.decode() for name in PAGES}

    def test_feuille_tailwind_compilee(self):
        for name, html in self.pages().items():
            with self.subTest(page=name):
                self.assertEqual(
                    html.count(
                        '<link rel="stylesheet" href="/static/css/tailwind.css">'
                    ),
                    1,
                )
                self.assertNotIn("text/tailwindcss", html)

    def test_htmx_local_charge_une_fois(self):
        for name, html in self.pages().items():
            with self.subTest(page=name):
                self.assertEqual(
                    html.count('<script src="/static/vendor/htmx/htmx.min.js">'), 1
                )

    def test_aucun_script_externe(self):
        for name, html in self.pages().items():
            with self.subTest(page=name):
                sources = SCRIPT_SRC_REGEX.findall(html)
                self.assertTrue(sources)
                self.assertEqual(
                    [s for s in sources if not s.startswith("/static/")], []
                )

    def test_htmx_embarque_avec_licence_et_readme(self):
        for name in ("htmx.min.js", "LICENSE", "README.md"):
            with self.subTest(name=name):
                self.assertIsNotNone(finders.find(f"vendor/htmx/{name}"))

    def test_source_unique_de_la_feuille(self):
        """Thème, styles de base et animations des alertes : une seule source."""
        css = SOURCE_CSS.read_text(encoding="utf-8")

        self.assertIn('@import "tailwindcss" theme(static);', css)
        self.assertIn("@layer base {", css)
        self.assertIn(".alert__toast-progress {", css)
        self.assertEqual(settings.TAILWIND_CLI_SRC_CSS, "assets/css/source.css")
