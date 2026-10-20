"""Tests du calendrier mensuel des notes, sur l'accueil de note_taking (#88)."""

import re
from datetime import date, timedelta

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from note_taking.models import Note
from note_taking.services import process_note_parts


class MonthCalendarTests(TestCase):
    def build(self, year: int, month: int, today: date = date(2026, 10, 20)):
        from note_taking.note_calendar import month_calendar

        return month_calendar(year, month, today)

    def test_semaines_du_lundi_au_dimanche(self):
        calendar = self.build(2026, 10)

        self.assertTrue(all(len(week) == 7 for week in calendar.weeks))
        self.assertEqual(calendar.weeks[0][0].date, date(2026, 9, 28))
        self.assertEqual(calendar.weeks[-1][-1].date, date(2026, 11, 1))

    def test_jours_hors_du_mois_week_end_et_aujourd_hui(self):
        days = {day.date: day for week in self.build(2026, 10).weeks for day in week}

        self.assertFalse(days[date(2026, 9, 30)].in_month)
        self.assertTrue(days[date(2026, 10, 1)].in_month)
        self.assertTrue(days[date(2026, 10, 24)].is_weekend)
        self.assertFalse(days[date(2026, 10, 23)].is_weekend)
        self.assertTrue(days[date(2026, 10, 20)].is_today)
        self.assertTrue(days[date(2026, 10, 20)].can_create)
        self.assertFalse(days[date(2026, 10, 21)].can_create)

    def test_notes_et_projets_du_mois(self):
        note = Note.objects.create(date="2026-10-14", body="# Beta\nx\n# Alpha\ny")
        process_note_parts(note)

        days = {day.date: day for week in self.build(2026, 10).weeks for day in week}

        self.assertEqual(days[date(2026, 10, 14)].note, note)
        self.assertEqual(days[date(2026, 10, 14)].projects, ["Alpha", "Beta"])
        self.assertFalse(days[date(2026, 10, 14)].can_create)
        self.assertIsNone(days[date(2026, 10, 13)].note)

    def test_mois_precedent_et_suivant(self):
        calendar = self.build(2026, 1)

        self.assertEqual(calendar.previous, date(2025, 12, 1))
        self.assertEqual(calendar.next, date(2026, 2, 1))
        self.assertEqual(calendar.month, date(2026, 1, 1))


class IndexCalendarTests(TestCase):
    def get(self, query: str = ""):
        return self.client.get(reverse("note_taking:index") + query)

    def test_mois_courant_par_defaut(self):
        today = timezone.localdate()

        response = self.get()

        self.assertEqual(response.context["calendar"].month, today.replace(day=1))

    def test_mois_demande(self):
        note = Note.objects.create(date="2025-11-24", body="# Projet A\nx")
        process_note_parts(note)

        response = self.get("?mois=2025-11")

        self.assertContains(
            response, f'href="{reverse("note_taking:note_detail", args=[note.pk])}"'
        )
        self.assertContains(response, "Projet A")
        self.assertContains(response, 'href="?mois=2025-10"')
        self.assertContains(response, 'href="?mois=2025-12"')

    def test_mois_invalide_ignore(self):
        response = self.get("?mois=n-importe")

        self.assertEqual(
            response.context["calendar"].month, timezone.localdate().replace(day=1)
        )

    def test_creation_d_une_note_pour_un_jour_passe_sans_note(self):
        response = self.get("?mois=2025-11")

        self.assertContains(
            response, f'href="{reverse("note_taking:new_note")}?date=2025-11-12"'
        )

    def test_bouton_creer_la_note_du_jour(self):
        today = timezone.localdate()

        response = self.get()

        self.assertContains(response, "Créer la note du jour")
        self.assertContains(
            response,
            f'href="{reverse("note_taking:new_note")}?date={today.isoformat()}"',
        )

    def test_bouton_ouvrir_la_note_du_jour(self):
        note = Note.objects.create(date=timezone.localdate())

        response = self.get()

        self.assertContains(response, "Ouvrir la note du jour")
        self.assertContains(
            response, f'href="{reverse("note_taking:note_detail", args=[note.pk])}"'
        )

    def test_navigation_entre_les_mois_par_htmx(self):
        response = self.get("?mois=2025-11")

        self.assertContains(response, 'id="calendar"')
        self.assertContains(response, 'hx-boost="true"')
        self.assertContains(response, 'hx-select="#calendar"')


class CalendarDayLinkTests(TestCase):
    """La case entière d'un jour est cliquable, pas un élément de la case."""

    CELL_LINK = r'<a class="[^"]*min-h-24[^"]*" href="{href}"'

    def get(self, query: str) -> str:
        return self.client.get(reverse("note_taking:index") + query).content.decode()

    def test_case_d_un_jour_avec_note(self):
        note = Note.objects.create(date="2025-11-24", body="# Projet A\nx")
        process_note_parts(note)
        href = reverse("note_taking:note_detail", args=[note.pk])

        html = self.get("?mois=2025-11")

        self.assertRegex(html, self.CELL_LINK.format(href=re.escape(href)))

    def test_case_d_un_jour_sans_note(self):
        href = f"{reverse('note_taking:new_note')}?date=2025-11-12"

        html = self.get("?mois=2025-11")

        self.assertRegex(html, self.CELL_LINK.format(href=re.escape(href)))
        self.assertIn('aria-label="Créer la note du 12 novembre 2025"', html)

    def test_jour_futur_non_cliquable(self):
        future = timezone.localdate().replace(day=1) + timedelta(days=62)

        html = self.get(f"?mois={future:%Y-%m}")

        self.assertNotIn(f"?date={future.isoformat()}", html)


class CalendarMarkupTests(TestCase):
    """Calendrier en HTML sémantique : tableau, dates, navigation."""

    def get(self, query: str = "") -> str:
        return self.client.get(reverse("note_taking:index") + query).content.decode()

    def test_tableau_avec_jours_de_la_semaine_en_en_tete(self):
        html = self.get("?mois=2025-11")

        self.assertIn("<table", html)
        self.assertIn('<caption class="sr-only">', html)
        self.assertEqual(html.count('<th scope="col"'), 7)
        self.assertRegex(html, r'<abbr title="lundi"[^>]*>Lun</abbr>')
        self.assertEqual(html.count("<tr"), 1 + 5)

    def test_dates_balisees(self):
        html = self.get("?mois=2025-11")

        self.assertIn('<time datetime="2025-11-12">12</time>', html)

    def test_aujourd_hui_signale(self):
        html = self.get()

        self.assertEqual(html.count('aria-current="date"'), 1)

    def test_navigation_entre_les_mois(self):
        html = self.get("?mois=2025-11")

        self.assertIn('<nav aria-label="Mois"', html)

    def test_jours_futurs_visiblement_inactifs(self):
        future = timezone.localdate().replace(day=1) + timedelta(days=62)

        html = self.get(f"?mois={future:%Y-%m}")

        self.assertIn("cursor-not-allowed", html)
        self.assertIn("border-dashed", html)
