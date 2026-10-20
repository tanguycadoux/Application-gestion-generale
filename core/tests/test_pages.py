"""Tests des éléments communs : page d'accueil, gabarit de base, statiques."""

from django.contrib.staticfiles import finders
from django.test import TestCase
from django.urls import reverse

STATIC_FILES = ("core/alert_system.css", "core/alert_system.js")


class CommonPagesTests(TestCase):
    def test_pages_affichees(self):
        for url in (
            "/",
            reverse("note_taking:index"),
            reverse("todolist:index"),
            reverse("todolist:todo_list"),
        ):
            with self.subTest(url=url):
                self.assertEqual(self.client.get(url).status_code, 200)

    def test_gabarit_de_base_charge_les_statiques_communs(self):
        html = self.client.get("/").content.decode()

        for name in STATIC_FILES:
            with self.subTest(name=name):
                self.assertIn(f"/static/{name}", html)

    def test_statiques_communs_trouves(self):
        for name in STATIC_FILES:
            with self.subTest(name=name):
                self.assertIsNotNone(finders.find(name))

    def test_navigation_signale_la_page_courante(self):
        for url in (reverse("note_taking:index"), reverse("todolist:todo_list")):
            with self.subTest(url=url):
                response = self.client.get(url)

                self.assertContains(response, 'aria-current="page"', count=1)
