"""Tests de l'en-tête HTML du gabarit de base : lang, charset et viewport (#121)."""

from django.test import TestCase


class BaseHeadTests(TestCase):
    def setUp(self):
        self.html = self.client.get("/").content.decode()

    def test_langue_du_document(self):
        self.assertIn('<html lang="fr">', self.html)

    def test_charset_en_tete_du_head(self):
        head = self.html[self.html.index("<head>") + len("<head>") :]
        self.assertTrue(head.lstrip().startswith('<meta charset="utf-8">'))

    def test_viewport(self):
        self.assertIn(
            '<meta name="viewport" content="width=device-width, initial-scale=1">',
            self.html,
        )
