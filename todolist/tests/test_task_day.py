"""Page d'un jour du calendrier des tâches : toutes ses tâches (#181)."""

from datetime import datetime, timedelta

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from core.models import Project
from todolist.models import Task

TODAY = timezone.localdate()


class TaskDayPageTests(TestCase):
    def setUp(self):
        self.project = Project.objects.create(name="ASTERICS", color="teal")

    def task(self, title: str, **fields) -> Task:
        return Task.objects.create(title=title, project=self.project, **fields)

    def page(self, day=TODAY, query: str = "") -> str:
        response = self.client.get(reverse("todolist:task_day", args=[day]) + query)
        self.assertEqual(response.status_code, 200)
        return response.content.decode()

    def test_en_cours_a_l_echeance_terminee_a_la_completion(self):
        self.task("Échéance du jour", due_date=TODAY)
        self.task("Finie aujourd'hui", due_date=TODAY - timedelta(days=5), progress=100)
        self.task("Échéance demain", due_date=TODAY + timedelta(days=1))
        finished = self.task("Finie hier, échéance du jour", due_date=TODAY)
        finished.progress = 100
        finished.save()
        Task.objects.filter(pk=finished.pk).update(
            completed_at=timezone.make_aware(
                datetime.combine(TODAY - timedelta(days=1), datetime.min.time())
            )
        )

        html = self.page()

        self.assertIn("Échéance du jour", html)
        self.assertIn("Finie aujourd&#x27;hui", html)
        self.assertNotIn("Échéance demain", html)
        self.assertNotIn("Finie hier", html)

    def test_toutes_les_taches_au_dela_de_trois(self):
        for index in range(5):
            self.task(f"Tâche {index}", due_date=TODAY)

        html = self.page()

        for index in range(5):
            self.assertIn(f"Tâche {index}", html)
        self.assertIn("(5)", html)

    def test_sous_tache_sous_son_parent_attenue(self):
        parent = self.task("Parent", due_date=TODAY + timedelta(days=9))
        self.task("Enfant", parent=parent, due_date=TODAY)

        html = self.page()

        self.assertIn("Parent", html)
        self.assertIn("Enfant", html)
        self.assertIn("(1)", html)

    def test_titre_creation_et_navigation(self):
        html = self.page()
        day = TODAY.isoformat()

        self.assertIn("<h1", html)
        self.assertIn(f'href="{reverse("todolist:task_create")}?due={day}"', html)
        for other in (TODAY - timedelta(days=1), TODAY + timedelta(days=1)):
            self.assertIn(f'href="{reverse("todolist:task_day", args=[other])}"', html)
        self.assertIn(f'href="{reverse("todolist:index")}?month={day[:7]}"', html)

    def test_jour_sans_tache(self):
        self.assertIn("Aucune tâche ce jour-là.", self.page())

    def test_date_impossible(self):
        response = self.client.get("/tasks/day/2026-02-30/")

        self.assertEqual(response.status_code, 404)

    def test_tri(self):
        self.task("B", due_date=TODAY)
        self.task("A", due_date=TODAY)

        html = self.page(query="?sort=title")

        self.assertLess(html.index(">A<"), html.index(">B<"))


class CalendarLinksToDayTests(TestCase):
    def test_numero_du_jour_et_autres_taches_menent_au_jour(self):
        project = Project.objects.create(name="P")
        for index in range(5):
            Task.objects.create(title=f"T{index}", project=project, due_date=TODAY)

        html = self.client.get(reverse("todolist:index")).content.decode()
        url = reverse("todolist:task_day", args=[TODAY])

        self.assertEqual(html.count(f'href="{url}"'), 2)
        self.assertRegex(html, rf'<a [^>]*href="{url}"[^>]*>\+ 2 autres</a>')
