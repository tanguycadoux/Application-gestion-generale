"""Bloc « Note du jour » de l'accueil général (#233)."""

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from note_taking.models import Note


class TodayNoteBlockTests(TestCase):
    def test_sans_note_propose_de_la_creer(self):
        today = timezone.localdate()

        response = self.client.get(reverse("core:index"))

        self.assertContains(response, "Créer la note du jour")
        self.assertContains(
            response, f'href="{reverse("note_taking:new_note")}?date={today:%Y-%m-%d}"'
        )

    def test_avec_note_propose_de_l_ouvrir(self):
        today = timezone.localdate()
        Note.objects.create(date=today, body="# P\nx")

        response = self.client.get(reverse("core:index"))

        self.assertContains(response, "Ouvrir la note du jour")
        self.assertContains(
            response, f'href="{reverse("note_taking:note_detail", args=[today])}"'
        )
        self.assertNotContains(response, "Créer la note du jour")
