"""Tests de l'accès à la note du jour et du pré-remplissage de la date (#87)."""

from datetime import date, datetime
from unittest import mock
from zoneinfo import ZoneInfo

from django.conf import settings
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from note_taking.models import Note


class NoteTodayTests(TestCase):
    def test_ouvre_la_note_du_jour_si_elle_existe(self):
        note = Note.objects.create(date=timezone.localdate())

        response = self.client.get(reverse("note_taking:note_today"))

        self.assertRedirects(
            response, reverse("note_taking:note_detail", args=[note.pk])
        )

    def test_propose_de_la_creer_sinon(self):
        today = timezone.localdate()

        response = self.client.get(reverse("note_taking:note_today"))

        self.assertRedirects(
            response, f"{reverse('note_taking:new_note')}?date={today.isoformat()}"
        )

    def test_fuseau_horaire_de_l_application(self):
        self.assertEqual(settings.TIME_ZONE, "Europe/Paris")

    def test_date_du_jour_selon_le_fuseau(self):
        """À 23 h 30 UTC le 1er mars, il est déjà le 2 mars à Paris."""
        now = datetime(2026, 3, 1, 23, 30, tzinfo=ZoneInfo("UTC"))

        with mock.patch("django.utils.timezone.now", return_value=now):
            response = self.client.get(reverse("note_taking:note_today"))

        self.assertRedirects(
            response, f"{reverse('note_taking:new_note')}?date=2026-03-02"
        )

    def test_lien_dans_le_menu(self):
        response = self.client.get(reverse("note_taking:index"))

        self.assertContains(response, f'href="{reverse("note_taking:note_today")}"')


class NewNoteDatePrefillTests(TestCase):
    def get(self, query: str = ""):
        return self.client.get(reverse("note_taking:new_note") + query)

    def test_date_pre_remplie(self):
        response = self.get("?date=2026-03-02")

        self.assertContains(response, 'value="2026-03-02"')

    def test_corps_vide(self):
        response = self.get("?date=2026-03-02")

        self.assertEqual(response.context["form"]["body"].value() or "", "")

    def test_date_invalide_ignoree(self):
        response = self.get("?date=pas-une-date")

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "pas-une-date")

    def test_note_existante_ouverte(self):
        note = Note.objects.create(date=date(2026, 3, 2))

        response = self.get("?date=2026-03-02")

        self.assertRedirects(
            response, reverse("note_taking:note_detail", args=[note.pk])
        )
