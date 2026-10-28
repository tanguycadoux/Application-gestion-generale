"""Barre de recherche de l'en-tête général, Ctrl+K (#202, #355)."""

import re
from pathlib import Path

from django.test import SimpleTestCase, TestCase
from django.urls import reverse

from core.app_registry import nav_sections, search_page


class SearchBarTests(TestCase):
    url = reverse("note_taking:notes_search")

    def page(self, url="/") -> str:
        return self.client.get(url).content.decode()

    def header(self, url="/") -> str:
        match = re.search(r"<header .*?</header>", self.page(url), re.S)
        assert match is not None
        return match.group()

    def nav(self, url="/") -> str:
        match = re.search(r"<nav .*?</nav>", self.page(url), re.S)
        assert match is not None
        return match.group()

    def test_page_de_recherche_declaree_par_une_app(self):
        page = search_page()

        self.assertIsNotNone(page)
        self.assertEqual(page.url_name, "note_taking:notes_search")

    def test_formulaire_get_vers_la_page_de_recherche(self):
        header = self.header()

        form = re.search(r"<search.*?<form ([^>]*)>", header, re.S).group(1)
        self.assertIn('method="get"', form)
        self.assertIn(f'action="{self.url}"', form)

    def test_champ_nomme_q_avec_son_libelle(self):
        header = self.header()

        field = re.search(r'<input type="search"[^>]*>', header).group()
        self.assertIn('name="q"', field)
        self.assertIn('aria-keyshortcuts="Control+K Meta+K"', field)
        self.assertRegex(header, r'<label for="nav-search" class="sr-only">')

    def test_indice_du_raccourci_en_police_mono(self):
        hint = re.search(
            r"<kbd [^>]*data-search-shortcut[^>]*>Ctrl K</kbd>", self.header()
        )

        self.assertIsNotNone(hint)
        self.assertIn("font-mono", hint.group())
        self.assertNotIn("font-sans", hint.group())

    def test_la_barre_est_dans_l_en_tete_pas_dans_le_menu(self):
        self.assertIn("<search", self.header())
        self.assertNotIn("<search", self.nav())
        self.assertNotIn('type="search"', self.nav())

    def test_barre_centree_et_de_largeur_bornee(self):
        header = self.header()

        search = re.search(r"<search[^>]*>", header).group()
        self.assertRegex(search, r"max-w-\S+")
        self.assertIn("mx-auto", search)

    def test_barre_toujours_visible_menu_replie(self):
        """Plus d'icône de recherche dans le menu : la barre est dans l'en-tête."""
        html = self.page()

        self.assertNotIn("data-search-link", html)
        self.assertNotIn('group-data-collapsed/nav:hidden" data-search', html)
        search = re.search(r"<search[^>]*>", html).group()
        self.assertNotIn("group-data-collapsed", search)

    def test_pas_de_barre_sur_la_page_de_recherche(self):
        html = self.page(self.url)

        header = re.search(r"<header .*?</header>", html, re.S).group()
        self.assertNotIn("data-search-input", header)
        self.assertNotIn("data-search-shortcut", html)

    def test_la_page_de_recherche_n_est_plus_dans_le_menu(self):
        urls = [item.url_name for section in nav_sections() for item in section.items]

        self.assertNotIn("note_taking:notes_search", urls)

    def test_script_du_raccourci_charge(self):
        self.assertIn(
            '<script src="/static/core/search.js" defer></script>', self.page()
        )

    def test_la_barre_marche_sans_javascript(self):
        """Le champ est un vrai formulaire GET : rien ne dépend du script."""
        header = self.header()

        self.assertNotRegex(header, r"<search[^>]*\shidden[\s>]")
        self.assertNotRegex(header, r"<form [^>]*data-hx-")


class SearchScriptTests(SimpleTestCase):
    script = (Path(__file__).parents[1] / "static/core/search.js").read_text(
        encoding="utf-8"
    )

    def test_ctrl_k_cherche_la_barre_puis_le_champ_de_la_page(self):
        self.assertIn("[data-search-input]", self.script)
        self.assertIn('input[type="search"][name="q"]', self.script)

    def test_plus_de_lien_de_repli(self):
        self.assertNotIn("data-search-link", self.script)
        self.assertNotIn("window.location", self.script)
