"""Le bilan d'une semaine : son adresse, sa navigation et ses blocs (#208)."""

from datetime import date, timedelta

from django.test import SimpleTestCase, TestCase
from django.urls import reverse
from django.utils import timezone


class WeekTests(SimpleTestCase):
    def week(self, day: date):
        from core.weeks import Week

        return Week.of(day)

    def test_du_lundi_au_dimanche(self):
        for day in (date(2025, 11, 24), date(2025, 11, 27), date(2025, 11, 30)):
            with self.subTest(day=day):
                week = self.week(day)
                self.assertEqual(
                    (week.monday, week.sunday), (date(2025, 11, 24), date(2025, 11, 30))
                )
                self.assertEqual(week.slug, "2025-W48")

    def test_a_cheval_sur_deux_annees(self):
        """Le numéro suit l'année ISO : le 29 décembre 2025 est en semaine 1 de 2026."""
        week = self.week(date(2025, 12, 31))

        self.assertEqual(week.slug, "2026-W01")
        self.assertEqual(week, self.week(date(2026, 1, 4)))
        self.assertEqual(week.previous.slug, "2025-W52")

    def test_annee_de_53_semaines(self):
        self.assertEqual(self.week(date(2026, 12, 31)).slug, "2026-W53")
        self.assertEqual(self.week(date(2026, 12, 31)).next.slug, "2027-W01")

    def test_libelle(self):
        cases = {
            date(2025, 11, 24): "du 24 au 30 novembre 2025",
            date(2025, 12, 1): "du 1er au 7 décembre 2025",
            date(2025, 10, 1): "du 29 septembre au 5 octobre 2025",
            date(2025, 12, 31): "du 29 décembre 2025 au 4 janvier 2026",
        }
        for day, label in cases.items():
            with self.subTest(day=day):
                self.assertEqual(self.week(day).label, label)

    def test_bornes_a_minuit_a_l_heure_locale(self):
        """Semaine du passage à l'heure d'hiver : les deux décalages."""
        week = self.week(date(2025, 10, 26))

        self.assertEqual(week.start.isoformat(), "2025-10-20T00:00:00+02:00")
        self.assertEqual(week.end.isoformat(), "2025-10-27T00:00:00+01:00")

    def test_sans_voisine_aux_bords(self):
        self.assertIsNone(self.week(date(1900, 1, 1)).previous)
        self.assertIsNone(self.week(date(2999, 12, 25)).next)


class WeekPageTests(TestCase):
    def get(self, slug: str) -> str:
        response = self.client.get(f"/week/{slug}/")
        self.assertEqual(response.status_code, 200)
        return response.content.decode()

    def test_semaine_dans_l_adresse(self):
        html = self.get("2025-W48")

        self.assertIn(">Semaine du 24 au 30 novembre 2025</h1>", html)
        self.assertIn("Semaine 48", html)

    def test_navigation(self):
        html = self.get("2026-W01")

        self.assertIn('href="/week/2025-W52/"', html)
        self.assertIn('href="/week/2026-W02/"', html)
        self.assertIn(f'href="{reverse("core:week_current")}"', html)

    def test_sans_adresse_la_semaine_en_cours(self):
        from core.weeks import Week

        html = self.client.get(reverse("core:week_current")).content.decode()

        self.assertIn(Week.of(timezone.localdate()).label, html)

    def test_lien_depuis_l_accueil(self):
        html = self.client.get(reverse("core:index")).content.decode()

        self.assertIn(f'href="{reverse("core:week_current")}"', html)

    def test_semaine_impossible_introuvable(self):
        for slug in (
            "2025-W53",
            "2025-W00",
            "2025-W54",
            "0001-W01",
            "9999-W52",
            "2025-48",
            "abc",
        ):
            with self.subTest(slug=slug):
                self.assertEqual(self.client.get(f"/week/{slug}/").status_code, 404)

    def test_bords_affiches(self):
        self.get("1900-W01")
        self.get("2999-W52")

    def test_blocs_des_apps_nommes(self):
        html = self.get("2025-W48")

        self.assertLess(html.index(">Notes</h2>"), html.index(">Tâches</h2>"))
        self.assertIn('<section aria-labelledby="week-block-1"', html)

    def test_semaine_vide(self):
        html = self.get("2025-W48")

        self.assertIn("Aucune note cette semaine.", html)
        self.assertIn("Aucune tâche terminée.", html)
        self.assertIn("Aucune tâche créée.", html)

    def test_semaine_a_venir(self):
        from core.weeks import Week

        later = timezone.localdate() + timedelta(days=21)

        self.assertIn("Aucune note cette semaine.", self.get(Week.of(later).slug))
