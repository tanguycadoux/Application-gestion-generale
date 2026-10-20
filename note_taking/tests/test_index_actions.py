"""Tests des actions de l'accueil des notes : pas de bouton « Nouvelle note » (#144)."""

import unittest

from django.test import TestCase
from django.urls import reverse


class IndexActionsTests(TestCase):
    def setUp(self):
        self.response = self.client.get(reverse("note_taking:index"))

    @unittest.expectedFailure
    def test_pas_de_bouton_nouvelle_note(self):
        self.assertNotContains(self.response, "Nouvelle note")
        self.assertNotContains(
            self.response, f'href="{reverse("note_taking:new_note")}"'
        )

    def test_note_du_jour_toujours_proposee(self):
        self.assertContains(self.response, "note du jour")
