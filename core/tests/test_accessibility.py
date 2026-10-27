"""Accessibilité du gabarit de base et des accueils (#191)."""

import re

from django.test import TestCase
from django.urls import reverse

PAGES = ("core:index", "core:projects", "note_taking:index", "todolist:index")


class BaseTemplateTests(TestCase):
    def pages(self) -> dict[str, str]:
        return {name: self.client.get(reverse(name)).content.decode() for name in PAGES}

    def test_menu_principal_nomme(self):
        for name, html in self.pages().items():
            with self.subTest(page=name):
                self.assertRegex(html, r'<nav [^>]*aria-label="Menu principal"')

    def test_lien_d_evitement_en_tete_vers_le_contenu(self):
        for name, html in self.pages().items():
            with self.subTest(page=name):
                body = html[html.index("<body") :]
                first_link = re.search(r"<a [^>]*>[^<]*</a>", body)
                assert first_link is not None
                self.assertIn('href="#contenu"', first_link.group())
                self.assertIn("Aller au contenu", first_link.group())
                self.assertIn("sr-only focus:not-sr-only", first_link.group())
                self.assertIn('<main id="contenu"', html)


class HomeTitleTests(TestCase):
    """Le titre d'onglet d'un accueil d'app est son titre de page."""

    def test_titre_d_onglet_egal_au_titre_de_page(self):
        for name, title in (
            ("note_taking:index", "Gestion des notes"),
            ("todolist:index", "Gestion des tâches"),
        ):
            with self.subTest(page=name):
                html = self.client.get(reverse(name)).content.decode()
                self.assertIn(f"<title>{title}</title>", html)
                self.assertRegex(html, rf"<h1[^>]*>{title}</h1>")
