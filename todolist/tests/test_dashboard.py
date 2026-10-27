"""Bloc des tâches en retard ou à échéance proche de l'accueil général (#233)."""

from datetime import timedelta

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from core.models import Project
from todolist.models import SOON_DAYS, Todo


class DueTasksBlockTests(TestCase):
    def setUp(self):
        self.today = timezone.localdate()
        self.project = Project.objects.create(name="ASTERICS", color="teal")

    def task(self, title, days=None, **fields):
        due = None if days is None else self.today + timedelta(days=days)
        return Todo.objects.create(
            title=title, project=self.project, due_date=due, **fields
        )

    def html(self):
        return self.client.get(reverse("core:index")).content.decode()

    def test_en_retard_et_proches_dans_l_ordre_des_echeances(self):
        self.task("Plus tard", SOON_DAYS)
        self.task("Hier", -1)
        self.task("Aujourdhui", 0)

        html = self.html()

        titles = ("Hier", "Aujourdhui", "Plus tard")
        positions = [html.index(title) for title in titles]
        self.assertEqual(positions, sorted(positions))

    def test_ni_lointaines_ni_sans_echeance_ni_terminees_ni_ecartees(self):
        self.task("Lointaine", SOON_DAYS + 1)
        self.task("Sans date")
        self.task("Faite", -2, done=True, progress=100)
        self.task("Écartée", -2, note_state="dismissed")

        html = self.html()

        for title in ("Lointaine", "Sans date", "Faite", "Écartée"):
            with self.subTest(title=title):
                self.assertNotIn(title, html)
        self.assertIn("Aucune tâche en retard ni à échéance proche.", html)

    def test_lien_vers_la_tache_et_temps_restant(self):
        todo = self.task("Relire", -2)

        response = self.client.get(reverse("core:index"))

        self.assertContains(
            response, f'href="{reverse("todolist:todo_detail", args=[todo.pk])}"'
        )
        self.assertContains(response, "2 j de retard")

    def test_lien_vers_la_liste(self):
        self.task("Relire", 0)

        response = self.client.get(reverse("core:index"))

        self.assertContains(response, f'href="{reverse("todolist:todo_list")}"')

    def test_au_plus_dix_puis_le_nombre_des_autres(self):
        for number in range(12):
            self.task(f"Retard {number:02d}", -number - 1)

        html = self.html()

        # Les plus en retard d'abord : « Retard 11 » (échéance il y a 12 jours) à
        # « Retard 02 » sont montrées, « Retard 01 » et « Retard 00 » restent.
        self.assertIn("Retard 11", html)
        self.assertIn("Retard 02", html)
        self.assertNotIn("Retard 01", html)
        self.assertNotIn("Retard 00", html)
        self.assertIn("et 2 autres", html)
