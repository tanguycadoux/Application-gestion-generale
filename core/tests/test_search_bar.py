"""Barre de recherche du menu commun, Ctrl+K (#202)."""

import re

from django.test import TestCase
from django.urls import reverse

from core.app_registry import nav_sections, search_page


class SearchBarTests(TestCase):
    url = reverse("note_taking:notes_search")

    def nav(self, url="/") -> str:
        html = self.client.get(url).content.decode()
        match = re.search(r"<nav .*?</nav>", html, re.S)
        assert match is not None
        return match.group()

    def test_page_de_recherche_declaree_par_une_app(self):
        page = search_page()

        self.assertIsNotNone(page)
        self.assertEqual(page.url_name, "note_taking:notes_search")

    def test_formulaire_get_vers_la_page_de_recherche(self):
        nav = self.nav()

        form = re.search(r"<search.*?<form ([^>]*)>", nav, re.S).group(1)
        self.assertIn('method="get"', form)
        self.assertIn(f'action="{self.url}"', form)

    def test_champ_nomme_q_avec_son_libelle(self):
        nav = self.nav()

        field = re.search(r'<input type="search"[^>]*>', nav).group()
        self.assertIn('name="q"', field)
        self.assertIn('aria-keyshortcuts="Control+K Meta+K"', field)
        self.assertRegex(nav, r'<label for="nav-search" class="sr-only">')

    def test_indice_du_raccourci(self):
        self.assertIn("Ctrl K", self.nav())

    def test_barre_au_dessus_des_sections(self):
        nav = self.nav()

        self.assertLess(nav.index("<search"), nav.index('id="nav-section-1"'))

    def test_icone_pour_le_menu_replie(self):
        nav = self.nav()

        link = re.search(r"<a [^>]*data-search-link[^>]*>", nav).group()
        self.assertIn(f'href="{self.url}"', link)
        self.assertIn('aria-label="', link)
        self.assertIn("group-data-collapsed/nav:flex", link)

    def test_barre_masquee_quand_le_menu_est_replie(self):
        nav = self.nav()

        search = re.search(r"<search[^>]*>", nav).group()
        self.assertIn("group-data-collapsed/nav:hidden", search)

    def test_pas_de_barre_sur_la_page_de_recherche(self):
        nav = self.nav(self.url)

        self.assertNotIn("<search", nav)
        self.assertNotIn("data-search-link", nav)

    def test_la_page_de_recherche_n_est_plus_dans_le_menu(self):
        urls = [item.url_name for section in nav_sections() for item in section.items]

        self.assertNotIn("note_taking:notes_search", urls)

    def test_script_du_raccourci_charge(self):
        html = self.client.get("/").content.decode()

        self.assertIn('<script src="/static/core/search.js" defer></script>', html)

    def test_la_barre_marche_sans_javascript(self):
        """Le champ est un vrai formulaire GET : rien ne dépend du script."""
        nav = self.nav()

        self.assertNotRegex(nav, r"<search[^>]*\shidden[\s>]")
        self.assertNotRegex(nav, r"<form [^>]*data-hx-")
