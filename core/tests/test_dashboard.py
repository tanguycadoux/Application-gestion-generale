"""Accueil général : un tableau de bord dont chaque app fournit ses blocs (#233)."""

from django.test import TestCase
from django.urls import reverse

from core.app_registry import DashboardBlock, dashboard_blocks


class DashboardTests(TestCase):
    def test_blocs_ranges_par_ordre(self):
        titles = [block.title for block in dashboard_blocks()]

        self.assertEqual(titles, ["Note du jour", "Tâches à échéance proche"])

    def test_accueil_affiche_un_bloc_par_titre(self):
        html = self.client.get(reverse("core:index")).content.decode()

        positions = [
            html.index(f">{title}</h2>")
            for title in ("Note du jour", "Tâches à échéance proche")
        ]
        self.assertEqual(positions, sorted(positions))

    def test_blocs_nommes_pour_les_lecteurs_d_ecran(self):
        html = self.client.get(reverse("core:index")).content.decode()

        self.assertIn('<section aria-labelledby="dashboard-block-1"', html)
        self.assertIn('<h2 id="dashboard-block-1"', html)

    def test_bloc_vide_sans_donnees(self):
        response = self.client.get(reverse("core:index"))

        self.assertContains(response, "Aucune tâche en retard ni à échéance proche.")

    def test_bloc_declare_par_une_app(self):
        block = DashboardBlock("Test", 5, "core/index.html", dict)

        self.assertEqual(block.context(), {})
