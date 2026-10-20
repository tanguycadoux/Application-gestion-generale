"""Tests de la mise en page du gabarit de base : sans panneau admin (#125)."""

from django.test import TestCase


class BaseLayoutTests(TestCase):
    def setUp(self):
        self.html = self.client.get("/").content.decode()

    def test_pas_de_panneau_admin(self):
        self.assertNotIn("Admin panel", self.html)
        self.assertNotIn('href="/admin/"', self.html)

    def test_grille_a_deux_colonnes(self):
        self.assertIn('<body class="font-sans grid grid-cols-[auto_1fr]', self.html)

    def test_admin_toujours_accessible_par_son_url(self):
        response = self.client.get("/admin/")

        self.assertRedirects(response, "/admin/login/?next=/admin/")
