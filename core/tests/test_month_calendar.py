"""Tests de la grille mensuelle et du composant de calendrier partagés (#167)."""

from dataclasses import dataclass
from datetime import date

from django.test import SimpleTestCase, TestCase
from django.urls import reverse


class MonthGridTests(SimpleTestCase):
    def test_grille_generique(self):
        from core.month_calendar import month_grid

        calendar = month_grid(2026, 10, today=date(2026, 10, 20))

        self.assertEqual(calendar.month, date(2026, 10, 1))
        self.assertEqual(
            (calendar.previous, calendar.next), (date(2026, 9, 1), date(2026, 11, 1))
        )
        self.assertEqual(calendar.weeks[0][0].date, date(2026, 9, 28))
        self.assertEqual(calendar.weeks[-1][-1].date, date(2026, 11, 1))
        self.assertTrue(all(len(week) == 7 for week in calendar.weeks))

    def test_changement_d_annee(self):
        from core.month_calendar import month_grid

        calendar = month_grid(2026, 1, today=date(2026, 10, 20))

        self.assertEqual(
            (calendar.previous, calendar.next), (date(2025, 12, 1), date(2026, 2, 1))
        )

    def test_type_de_case_fourni_par_l_app(self):
        from core.month_calendar import CalendarDay, month_grid

        @dataclass
        class CustomDay(CalendarDay):
            label: str = "vide"

        calendar = month_grid(2026, 10, today=date(2026, 10, 20), day_class=CustomDay)

        self.assertEqual(calendar.weeks[0][0].label, "vide")

    def test_mois_demande_ou_courant(self):
        from core.month_calendar import parse_month_param

        self.assertEqual(parse_month_param("2026-02"), (2026, 2))
        self.assertIsNone(parse_month_param("n-importe"))


class SharedComponentTests(TestCase):
    def test_les_deux_calendriers_utilisent_le_composant(self):
        for url in (reverse("note_taking:index"), reverse("todolist:index")):
            with self.subTest(url=url):
                html = self.client.get(url).content.decode()

                self.assertIn('data-component="month-calendar"', html)
                self.assertIn(
                    '<section id="calendar" aria-labelledby="calendar-title"', html
                )
