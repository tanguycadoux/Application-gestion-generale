"""Tests des couleurs : uniquement celles de Tailwind (#128).

Gris : slate ; couleurs : blue (principale), red (danger), amber (avertissement),
green (succès) ; plus white et black. Exception : les couleurs des callouts du
contenu des notes, reprises de Quarto.
"""

import re
from pathlib import Path

from django.conf import settings
from django.contrib.staticfiles import finders
from django.test import SimpleTestCase, TestCase

APPS = ("core", "images", "note_taking", "todolist")

ALLOWED_COLORS = {"slate", "blue", "red", "amber", "green", "white", "black"}

TAILWIND_COLORS = ALLOWED_COLORS | {
    "gray",
    "zinc",
    "neutral",
    "stone",
    "orange",
    "yellow",
    "lime",
    "emerald",
    "teal",
    "cyan",
    "sky",
    "indigo",
    "violet",
    "purple",
    "fuchsia",
    "pink",
    "rose",
}

COLOR_UTILITIES = (
    "bg|text|border(?:-[trblxy])?|outline|ring|fill|stroke|from|via|to|divide"
    "|decoration|accent|caret|shadow"
)

# Classe de couleur : bg-slate-200, hover:text-red-700, after:border-blue-500…
COLOR_CLASS_REGEX = re.compile(
    rf"(?<![\w-])(?:{COLOR_UTILITIES})-(?P<color>[a-z]+)(?:-\d+)?(?:/\d+)?(?![\w-])"
)
CUSTOM_PALETTE_REGEX = re.compile(r"\b(?:neutral|primary|alert|warning)-\d+\b")
ARBITRARY_COLOR_REGEX = re.compile(r"-\[(?:oklch|rgb|hsl|#)")

CSS_COMMENT_REGEX = re.compile(r"/\*.*?\*/", re.DOTALL)
CSS_VAR_COLOR_REGEX = re.compile(r"var\(--color-(?P<color>[a-z]+)(?:-\d+)?\)")
# Couleurs écrites en dur ; seules les ombres et voiles noirs transparents passent.
CSS_LITERAL_COLOR_REGEX = re.compile(
    r"#[0-9a-fA-F]{3,8}\b|(?:oklch|rgba?|hsla?)\((?!0[ ,]+0[ ,]+0[ ,]*[/,])[^)]*\)"
)


def app_sources() -> list[Path]:
    """Gabarits, code Python et scripts des applications, hors tests et migrations."""
    files: list[Path] = []
    for app in APPS:
        for pattern in ("**/*.html", "**/*.py", "**/*.js"):
            files += [
                path
                for path in (Path(settings.BASE_DIR) / app).glob(pattern)
                if "tests" not in path.parts and "migrations" not in path.parts
            ]
    return files


def read_static(name: str) -> str:
    path = finders.find(name)
    assert isinstance(path, str)
    return Path(path).read_text(encoding="utf-8")


class TailwindThemeTests(TestCase):
    def setUp(self):
        self.html = self.client.get("/").content.decode()

    def test_variables_de_couleur_de_tailwind_toujours_emises(self):
        """Les feuilles CSS propres utilisent var(--color-…) sans classe dans la page."""
        self.assertIn('@import "tailwindcss" theme(static);', self.html)

    def test_plus_de_palette_maison(self):
        self.assertNotIn("--color-primary-", self.html)
        self.assertNotIn("--color-neutral-", self.html)
        self.assertNotIn("--color-alert-", self.html)
        self.assertNotIn("--color-warning-", self.html)


class ColorClassesTests(SimpleTestCase):
    def test_sources_trouvees(self):
        self.assertGreater(len(app_sources()), 50)

    def test_pas_de_couleur_de_la_palette_maison(self):
        for path in app_sources():
            with self.subTest(path=str(path)):
                text = path.read_text(encoding="utf-8")
                self.assertEqual(CUSTOM_PALETTE_REGEX.findall(text), [])

    def test_pas_de_couleur_en_dur_dans_les_classes(self):
        for path in app_sources():
            with self.subTest(path=str(path)):
                text = path.read_text(encoding="utf-8")
                self.assertEqual(ARBITRARY_COLOR_REGEX.findall(text), [])

    def test_familles_de_couleurs_autorisees(self):
        for path in app_sources():
            with self.subTest(path=str(path)):
                colors = {
                    match.group("color")
                    for match in COLOR_CLASS_REGEX.finditer(
                        path.read_text(encoding="utf-8")
                    )
                    if match.group("color") in TAILWIND_COLORS
                }
                self.assertLessEqual(colors, ALLOWED_COLORS)


class StylesheetColorsTests(SimpleTestCase):
    def test_alertes_sans_couleur_en_dur(self):
        css = CSS_COMMENT_REGEX.sub("", read_static("core/alert_system.css"))

        self.assertEqual(CSS_LITERAL_COLOR_REGEX.findall(css), [])
        colors = {m.group("color") for m in CSS_VAR_COLOR_REGEX.finditer(css)}
        self.assertLessEqual(colors, ALLOWED_COLORS)

    def test_contenu_des_notes_seuls_les_callouts_en_dur(self):
        css = read_static("note_taking/style.css")

        for line in CSS_COMMENT_REGEX.sub("", css).splitlines():
            if CSS_LITERAL_COLOR_REGEX.search(line):
                with self.subTest(line=line.strip()):
                    self.assertRegex(line, r"^\.callout-\w+\s*\{ --callout-color: #")
        colors = {m.group("color") for m in CSS_VAR_COLOR_REGEX.finditer(css)}
        self.assertLessEqual(colors, ALLOWED_COLORS)
