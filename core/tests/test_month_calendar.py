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


class ReservedHeightTests(TestCase):
    """Un mois occupe toujours la place de six semaines (#275)."""

    def test_semaines_de_reserve(self):
        from core.month_calendar import month_grid

        today = date(2026, 10, 1)
        for (year, month), weeks, spare in (
            ((2027, 2), 4, 2),
            ((2026, 10), 5, 1),
            ((2026, 11), 6, 0),
        ):
            with self.subTest(month=month, year=year):
                calendar = month_grid(year, month, today)

                self.assertEqual(len(calendar.weeks), weeks)
                self.assertEqual(len(calendar.spare_weeks), spare)

    def test_toujours_six_lignes_dans_les_deux_calendriers(self):
        for url in (reverse("note_taking:index"), reverse("todolist:index")):
            for month, spare in (("2027-02", 2), ("2026-10", 1), ("2026-11", 0)):
                with self.subTest(url=url, month=month):
                    html = self.client.get(url, {"month": month}).content.decode()
                    body = html.split("<tbody>")[1].split("</tbody>")[0]

                    self.assertEqual(body.count("<tr"), 6)
                    self.assertEqual(body.count("data-spare-week"), spare)

    def test_semaine_de_reserve_cachee_aux_technologies_d_assistance(self):
        html = self.client.get(
            reverse("note_taking:index"), {"month": "2027-02"}
        ).content.decode()

        self.assertIn('<tr aria-hidden="true" data-spare-week>', html)


class SharedComponentTests(TestCase):
    def test_les_deux_calendriers_utilisent_le_composant(self):
        for url in (reverse("note_taking:index"), reverse("todolist:index")):
            with self.subTest(url=url):
                html = self.client.get(url).content.decode()

                self.assertIn('data-component="month-calendar"', html)
                self.assertIn(
                    '<section id="calendar" aria-labelledby="calendar-title"', html
                )
