"""Icônes Material Symbols en SVG inline, sans police externe (#218)."""

import re
import socket
import tempfile
import unittest
from io import StringIO
from pathlib import Path
from unittest.mock import patch

from django.conf import settings
from django.core.management import call_command
from django.template import Context, Template, TemplateSyntaxError
from django.test import SimpleTestCase, TestCase
from django.urls import reverse

APPS = ("core", "images", "note_taking", "todolist")
ICONS_DIR = Path(settings.BASE_DIR) / "static" / "icons"

ICON_TAG_REGEX = re.compile(r'\{% icon "(?P<name>[a-z0-9_]+)"')
ICON_PARAM_REGEX = re.compile(r'\bicon="(?P<name>[a-z0-9_]+)"')
NAV_LINK_REGEX = re.compile(r'\{% nav_link "[^"]+" "[^"]+" "(?P<name>[a-z0-9_]+)" %\}')
ALERT_ICON_REGEX = re.compile(r'icon: "(?P<name>[a-z0-9_]+)"')

SVG = (
    '<svg xmlns="http://www.w3.org/2000/svg" height="24" viewBox="0 -960 960 960" '
    'width="24"><path d="M0 0h1v1z"/></svg>'
)


def render(template: str) -> str:
    return Template("{% load ui %}" + template).render(Context())


def app_files(*patterns: str) -> list[Path]:
    return [
        path
        for app in APPS
        for pattern in patterns
        for path in (Path(settings.BASE_DIR) / app).glob(pattern)
        if "tests" not in path.parts and "migrations" not in path.parts
    ]


def used_icons() -> set[str]:
    """Icônes citées par les gabarits, les composants, le rendu et les alertes."""
    from core.app_registry import home_links
    from note_taking.rendering import CALLOUT_ICONS

    names: set[str] = set(CALLOUT_ICONS.values())
    names |= {link.icon for link in home_links()}
    for path in app_files("**/*.html", "**/*.py", "**/*.js"):
        text = path.read_text(encoding="utf-8")
        for regex in (
            ICON_TAG_REGEX,
            ICON_PARAM_REGEX,
            NAV_LINK_REGEX,
            ALERT_ICON_REGEX,
        ):
            names |= {match.group("name") for match in regex.finditer(text)}
    return names


class IconComponentTests(SimpleTestCase):
    @unittest.expectedFailure
    def test_icone_decorative(self):
        html = render('{% icon "save" %}')

        self.assertTrue(html.startswith("<svg "))
        self.assertIn('fill="currentColor"', html)
        self.assertIn('aria-hidden="true"', html)
        self.assertIn('focusable="false"', html)
        self.assertIn('viewBox="0 -960 960 960"', html)
        self.assertIn("<path ", html)
        self.assertNotIn("role=", html)

    @unittest.expectedFailure
    def test_icone_seule_avec_libelle(self):
        html = render('{% icon "warning" label="Incohérences à corriger" %}')

        self.assertIn('role="img"', html)
        self.assertIn('aria-label="Incohérences à corriger"', html)
        self.assertNotIn("aria-hidden", html)

    @unittest.expectedFailure
    def test_taille_par_classe(self):
        self.assertIn('class="size-6 shrink-0"', render('{% icon "save" %}'))
        self.assertIn(
            'class="size-4 text-amber-600"',
            render('{% icon "save" class="size-4 text-amber-600" %}'),
        )

    @unittest.expectedFailure
    def test_icone_inconnue_refusee(self):
        with self.assertRaisesMessage(TemplateSyntaxError, "add_icon"):
            render('{% icon "nexistepas" %}')


class IconFilesTests(SimpleTestCase):
    def test_icones_utilisees_trouvees(self):
        self.assertGreater(len(used_icons()), 15)

    @unittest.expectedFailure
    def test_chaque_icone_utilisee_est_embarquee(self):
        for name in sorted(used_icons()):
            with self.subTest(name=name):
                self.assertTrue((ICONS_DIR / f"{name}.svg").exists())

    @unittest.expectedFailure
    def test_licence_et_readme(self):
        for name in ("LICENSE", "README.md"):
            with self.subTest(name=name):
                self.assertTrue((ICONS_DIR / name).exists())

    @unittest.expectedFailure
    def test_plus_de_police_d_icones(self):
        for path in [*app_files("**/*.html", "**/*.py", "**/*.js", "**/*.css")]:
            with self.subTest(path=str(path)):
                self.assertNotIn("material-symbols", path.read_text(encoding="utf-8"))


class AddIconCommandTests(SimpleTestCase):
    @unittest.expectedFailure
    def test_telecharge_l_icone_rounded(self):
        from core import icons

        with tempfile.TemporaryDirectory() as directory:
            response = unittest.mock.MagicMock()
            response.__enter__.return_value.read.return_value = SVG.encode()
            with (
                patch.object(icons, "ICONS_DIR", Path(directory)),
                patch("urllib.request.urlopen", return_value=response) as urlopen,
            ):
                call_command("add_icon", "bolt", stdout=StringIO())

            url = urlopen.call_args.args[0]
            self.assertIn("/materialsymbolsrounded/bolt_24px.svg", url)
            self.assertEqual((Path(directory) / "bolt.svg").read_text(), SVG)


class NoNetworkTests(SimpleTestCase):
    @unittest.expectedFailure
    def test_connexion_reseau_interdite_pendant_les_tests(self):
        with self.assertRaisesRegex(RuntimeError, "réseau"):
            socket.create_connection(("127.0.0.1", 9), timeout=1)


class FaviconTests(TestCase):
    @unittest.expectedFailure
    def test_icone_d_onglet_locale(self):
        html = self.client.get(reverse("core:index")).content.decode()

        self.assertIn(
            '<link rel="icon" href="/static/core/favicon.svg" type="image/svg+xml">',
            html,
        )
        self.assertTrue(
            (
                Path(settings.BASE_DIR) / "core" / "static" / "core" / "favicon.svg"
            ).exists()
        )
