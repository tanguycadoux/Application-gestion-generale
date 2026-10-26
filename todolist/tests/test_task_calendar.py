"""Tests du calendrier des tâches et de leur date de complétion (#167)."""

from datetime import date, datetime, timedelta

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from core.models import Project
from todolist.models import Todo

TODAY = timezone.localdate()


class CompletedAtTests(TestCase):
    def setUp(self):
        self.project = Project.objects.create(name="P")

    def task(self, **fields) -> Todo:
        return Todo.objects.create(title="T", project=self.project, **fields)

    def test_date_de_completion_a_la_completion(self):
        task = self.task()
        self.assertIsNone(task.completed_at)

        task.progress = 100
        task.save()
        self.assertEqual(timezone.localdate(task.completed_at), TODAY)

        task.progress = 50
        task.save()
        self.assertIsNone(task.completed_at)

    def test_date_conservee_si_la_tache_reste_terminee(self):
        moment = timezone.make_aware(datetime(2025, 11, 24, 10, 0))
        task = self.task(progress=100)
        Todo.objects.filter(pk=task.pk).update(completed_at=moment)
        task.refresh_from_db()

        task.title = "Renommée"
        task.save()

        self.assertEqual(task.completed_at, moment)

    def test_parent_decoche_automatiquement_perd_sa_date(self):
        parent = self.task()
        child = self.task(parent=parent, progress=100)
        parent.done = True
        parent.save()
        self.assertIsNotNone(Todo.objects.get(pk=parent.pk).completed_at)

        child.progress = 0
        child.save()

        self.assertIsNone(Todo.objects.get(pk=parent.pk).completed_at)


class TaskCalendarTests(TestCase):
    def setUp(self):
        self.project = Project.objects.create(name="ASTERICS", color="teal")

    def task(self, title: str, **fields) -> Todo:
        return Todo.objects.create(title=title, project=self.project, **fields)

    def day(self, when: date):
        from todolist.task_calendar import task_calendar

        calendar = task_calendar(when.year, when.month, TODAY)
        return {day.date: day for week in calendar.weeks for day in week}[when]

    def test_en_cours_a_l_echeance_terminee_a_la_completion(self):
        pending = self.task("En cours", due_date=TODAY + timedelta(days=2))
        done = self.task("Finie", due_date=TODAY + timedelta(days=2), progress=100)

        self.assertEqual(self.day(TODAY + timedelta(days=2)).tasks, [pending])
        self.assertEqual(self.day(TODAY).tasks, [done])

    def test_page_d_accueil_des_taches(self):
        self.task("Relire", due_date=TODAY)

        html = self.client.get(reverse("todolist:index")).content.decode()

        self.assertIn("<title>Gestion des tâches</title>", html)
        self.assertIn(">Relire<", html)
        self.assertIn("bg-teal-500", html)

    def test_au_plus_trois_taches_par_case(self):
        for index in range(5):
            self.task(f"Tâche {index}", due_date=TODAY)

        html = self.client.get(reverse("todolist:index")).content.decode()

        self.assertIn(">Tâche 2<", html)
        self.assertNotIn(">Tâche 3<", html)
        self.assertIn("+ 2 autres", html)

    def test_retard_et_terminee(self):
        self.task("En retard", due_date=TODAY - timedelta(days=1))
        self.task("Finie", progress=100)

        html = self.client.get(reverse("todolist:index")).content.decode()

        self.assertRegex(html, r'class="[^"]*text-red-800[^"]*"[^>]*>En retard<')
        self.assertRegex(html, r'class="[^"]*text-slate-500[^"]*"[^>]*>Finie<')

    def test_creation_d_une_tache_a_une_echeance(self):
        html = self.client.get(reverse("todolist:index")).content.decode()
        url = reverse("todolist:todo_create") + f"?due={TODAY.isoformat()}"

        self.assertIn(f'href="{url}"', html)
        form = self.client.get(url).content.decode()
        self.assertIn(f'value="{TODAY.isoformat()}"', form)
