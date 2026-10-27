"""Menu commun aux apps, repliable en icônes (#232)."""

import re

from django.test import TestCase
from django.urls import reverse

from core.app_registry import NavItem, NavSection, nav_sections


class NavigationTests(TestCase):
    def test_sections_rangees_par_ordre(self):
        self.assertEqual(
            [section.label for section in nav_sections()],
            ["Notes", "Tâches", "Projets"],
        )

    def test_chaque_entree_est_une_adresse_valide(self):
        for section in nav_sections():
            for item in section.items:
                with self.subTest(item=item.url_name):
                    self.assertTrue(reverse(item.url_name))

    def test_menu_identique_d_une_page_a_l_autre(self):
        def menu(url):
            html = self.client.get(url).content.decode()
            nav = re.search(r"<nav .*?</nav>", html, re.S).group()
            return re.sub(r'\s*aria-current="page"|\s*bg-white', "", nav)

        pages = ("/", reverse("note_taking:index"), reverse("todolist:todo_list"))
        self.assertEqual(len({menu(url) for url in pages}), 1)

    def test_pas_de_lien_toutes_les_apps(self):
        html = self.client.get(reverse("note_taking:index")).content.decode()

        self.assertNotIn("Toutes les apps", html)

    def test_libelle_en_aria_label_et_infobulle(self):
        html = self.client.get("/").content.decode()

        for item in (section.items[0] for section in nav_sections()):
            with self.subTest(item=item.label):
                self.assertRegex(
                    html,
                    rf'href="{reverse(item.url_name)}" title="{item.label}" '
                    rf'aria-label="{item.label}"',
                )

    def test_sections_nommees_pour_les_lecteurs_d_ecran(self):
        html = self.client.get("/").content.decode()

        for number in (1, 2, 3):
            self.assertIn(f'<ul aria-labelledby="nav-section-{number}">', html)
            self.assertIn(f'id="nav-section-{number}"', html)

    def test_bouton_de_repli_cache_sans_javascript(self):
        html = self.client.get("/").content.decode()

        button = re.search(r'<button type="button" id="nav-toggle"[^>]*>', html).group()
        self.assertIn(" hidden ", button)
        self.assertIn('aria-controls="main-nav"', button)
        self.assertIn('aria-expanded="true"', button)
        self.assertIn('<script src="/static/core/nav.js">', html)

    def test_page_courante_marquee(self):
        response = self.client.get(reverse("note_taking:notes_list"))

        self.assertContains(response, 'aria-current="page"', count=1)

    def test_section_declaree_par_une_app(self):
        section = NavSection("Test", 5, (NavItem("core:projects", "Liste", "folder"),))

        self.assertEqual(section.items[0].url_name, "core:projects")
