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
            ("note_taking:index", "Calendrier des notes"),
            ("todolist:index", "Calendrier des tâches"),
        ):
            with self.subTest(page=name):
                html = self.client.get(reverse(name)).content.decode()
                self.assertIn(f"<title>{title}</title>", html)
                self.assertRegex(html, rf"<h1[^>]*>{title}</h1>")

    def test_titre_correspond_a_l_entree_du_menu_marquee(self):
        """#378 : le titre dit ce que montre la page, et c'est l'entrée du menu
        marquée `aria-current`, dans sa section (« Notes › Calendrier »)."""
        for name, section, title in (
            ("note_taking:index", "Notes", "Calendrier des notes"),
            ("todolist:index", "Tâches", "Calendrier des tâches"),
        ):
            with self.subTest(page=name):
                html = self.client.get(reverse(name)).content.decode()
                nav = html[html.index('id="main-nav"') : html.index("</nav>")]
                current = re.search(r'<a [^>]*aria-current="page"[^>]*>', nav)
                assert current is not None
                self.assertIn('aria-label="Calendrier"', current.group())
                before = nav[: current.start()]
                headings = re.findall(
                    r'<p id="nav-section-\d+"[^>]*>([^<]*)</p>', before
                )
                self.assertEqual(headings[-1], section)
                self.assertEqual(title, f"Calendrier des {section.lower()}")
