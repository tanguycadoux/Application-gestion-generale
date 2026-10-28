"""En-tête général : accueil à gauche, recherche au centre (#355)."""

import re

from django.test import TestCase
from django.urls import reverse

PAGES = ("core:index", "core:projects", "note_taking:index", "todolist:index")


class HeaderTests(TestCase):
    def page(self, name="core:index") -> str:
        return self.client.get(reverse(name)).content.decode()

    def test_un_seul_en_tete_de_page_avant_le_menu_et_le_contenu(self):
        for name in PAGES:
            with self.subTest(page=name):
                html = self.page(name)
                body = html[html.index("<body") :]
                top = re.findall(r"<header [^>]*>", body.split("<main")[0])
                self.assertEqual(len(top), 1)
                self.assertLess(body.index("<header"), body.index("<nav"))
                self.assertLess(body.index("<nav"), body.index("<main"))

    def test_en_tete_sur_toute_la_largeur(self):
        html = self.page()

        header = re.search(r"<header [^>]*>", html).group()
        self.assertIn("col-span-2", header)
        body = re.search(r"<body [^>]*>", html).group()
        self.assertIn("grid-rows-[auto_minmax(0,1fr)]", body)
        self.assertIn("h-screen", body)

    def test_lien_d_evitement_reste_le_premier_element(self):
        html = self.page()

        body = html[html.index("<body") :]
        self.assertLess(body.index('href="#contenu"'), body.index("<header"))

    def test_nom_de_l_application_a_gauche_lien_vers_l_accueil(self):
        html = self.page("note_taking:index")

        header = re.search(r"<header .*?</header>", html, re.S).group()
        link = re.search(r'<a [^>]*href="/"[^>]*>.*?</a>', header, re.S).group()
        self.assertIn("Gestion générale", link)
        self.assertNotIn("<svg", link)
        self.assertLess(header.index('href="/"'), header.index("<search"))

    def test_accueil_n_est_plus_dans_le_menu(self):
        nav = re.search(r"<nav .*?</nav>", self.page(), re.S).group()

        self.assertNotIn("Accueil", nav)
        self.assertNotIn('href="/"', nav)

    def test_nom_se_comporte_comme_un_logo_sans_fond_ni_etat_actif(self):
        """Identique sur l'accueil et ailleurs : pas de fond, pas de `aria-current`."""
        links = set()
        for name in ("core:index", "note_taking:index"):
            header = re.search(r"<header .*?</header>", self.page(name), re.S).group()
            link = re.search(r'<a [^>]*href="/"[^>]*>', header).group()
            self.assertNotIn("aria-current", link)
            self.assertNotRegex(link, r"bg-")
            self.assertNotIn("hover:", link)
            links.add(link)
        self.assertEqual(len(links), 1)

    def test_recherche_au_centre_emplacement_a_droite(self):
        header = re.search(r"<header .*?</header>", self.page(), re.S).group()

        self.assertIn(
            "grid-cols-[1fr_minmax(0,", re.search(r"<header [^>]*>", header).group()
        )
        self.assertLess(header.index("<search"), header.index('id="header-end"'))

    def test_un_seul_repere_banniere_et_un_seul_menu_et_contenu(self):
        html = self.page()

        self.assertEqual(html.count('aria-label="Menu principal"'), 1)
        self.assertEqual(html.count("<main "), 1)

    def test_menu_commence_par_les_sections(self):
        nav = re.search(r"<nav .*?</nav>", self.page(), re.S).group()

        self.assertLess(nav.index('id="nav-section-1"'), nav.index("<ul"))
        self.assertEqual(len(re.findall(r"<ul[ >]", nav)), 3)
