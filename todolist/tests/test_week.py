"""Les tâches d'une semaine : terminées, créées, en retard (#208)."""

import re
from datetime import date, datetime, timedelta
from unittest import expectedFailure

from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.utils import timezone

from core.models import Project
from todolist.models import Task

# Semaine 48 de 2025 : du lundi 24 au dimanche 30 novembre.
BEFORE, MONDAY, SUNDAY, AFTER = (
    date(2025, 11, 23),
    date(2025, 11, 24),
    date(2025, 11, 30),
    date(2025, 12, 1),
)


def at(day: date, hour: int = 12, minute: int = 0) -> datetime:
    """Ce jour à cette heure, à l'heure locale."""
    return timezone.make_aware(datetime(day.year, day.month, day.day, hour, minute))


class WeekTasksTestCase(TestCase):
    def setUp(self):
        self.project = Project.objects.create(name="P")

    def task(
        self,
        title: str,
        created: datetime | None = None,
        completed: datetime | None = None,
        due: date | None = None,
    ) -> Task:
        task = Task.objects.create(
            title=title,
            project=self.project,
            due_date=due,
            progress=100 if completed else 0,
        )
        Task.objects.filter(pk=task.pk).update(
            created_at=created or at(date(2025, 1, 1)), completed_at=completed
        )
        return task

    def html(self, slug: str = "2025-W48") -> str:
        response = self.client.get(f"/week/{slug}/")
        self.assertEqual(response.status_code, 200)
        return response.content.decode()

    def titles(self, rubric: str, slug: str = "2025-W48") -> list[str]:
        """Les tâches d'une rubrique (`done`, `created`, `late`)."""
        html = self.html(slug)
        self.assertIn(f'aria-labelledby="week-{rubric}"', html)
        section = html.split(f'aria-labelledby="week-{rubric}"')[1]
        return re.findall(
            r'href="/tasks/\d+/"[^>]*>(.*?)</a>', section.split("</section>")[0]
        )


class DoneTests(WeekTasksTestCase):
    @expectedFailure
    def test_terminees_dans_la_semaine_par_date(self):
        self.task("Mardi", completed=at(date(2025, 11, 25)))
        self.task("Avant", completed=at(BEFORE))
        self.task("Lundi", completed=at(MONDAY))
        self.task("Après", completed=at(AFTER))
        self.task("En cours")

        self.assertEqual(self.titles("done"), ["Lundi", "Mardi"])

    @expectedFailure
    def test_heure_locale(self):
        """Lundi 0 h 30 à Paris est encore dimanche en temps universel."""
        self.task("Début", completed=at(MONDAY, 0, 30))
        self.task("Fin", completed=at(SUNDAY, 23, 30))
        self.task("Trop tôt", completed=at(BEFORE, 23, 30))
        self.task("Trop tard", completed=at(AFTER, 0, 30))

        self.assertEqual(self.titles("done"), ["Début", "Fin"])


class CreatedTests(WeekTasksTestCase):
    @expectedFailure
    def test_creees_dans_la_semaine_heure_locale(self):
        self.task("Début", created=at(MONDAY, 0, 30))
        self.task("Fin", created=at(SUNDAY, 23, 30))
        self.task("Trop tôt", created=at(BEFORE, 23, 30))
        self.task("Trop tard", created=at(AFTER, 0, 30))

        self.assertEqual(self.titles("created"), ["Début", "Fin"])

    @expectedFailure
    def test_creee_et_terminee_dans_les_deux(self):
        self.task("T", created=at(MONDAY), completed=at(SUNDAY))

        self.assertEqual(self.titles("created"), ["T"])
        self.assertEqual(self.titles("done"), ["T"])

    @expectedFailure
    def test_ecartee_absente(self):
        task = self.task("T", created=at(MONDAY), completed=at(MONDAY), due=BEFORE)
        Task.all_objects.filter(pk=task.pk).update(note_state=Task.NoteState.DISMISSED)

        for rubric in ("done", "created", "late"):
            self.assertEqual(self.titles(rubric), [])


class LateTests(WeekTasksTestCase):
    """En retard : à la fin de la semaine, ou aujourd'hui pour celle en cours."""

    @expectedFailure
    def test_semaine_passee_a_sa_fin(self):
        self.task("Dans la semaine", due=SUNDAY)
        self.task("Avant", due=BEFORE)
        self.task("Pas encore", due=AFTER)
        self.task("Sans échéance")

        self.assertEqual(self.titles("late"), ["Avant", "Dans la semaine"])

    @expectedFailure
    def test_terminee_depuis_etait_en_retard(self):
        self.task("Depuis", due=MONDAY, completed=at(AFTER, 0, 30))
        self.task("À temps", due=MONDAY, completed=at(SUNDAY, 23, 30))

        self.assertEqual(self.titles("late"), ["Depuis"])
        self.assertIn("terminée depuis, le", self.html())

    @expectedFailure
    def test_creee_apres_la_semaine_absente(self):
        self.task("Trop tard", due=MONDAY, created=at(AFTER))

        self.assertEqual(self.titles("late"), [])

    @expectedFailure
    def test_semaine_en_cours_a_aujourd_hui(self):
        from core.weeks import Week

        today = timezone.localdate()
        self.task("Hier", due=today - timedelta(days=1))
        self.task("Aujourd'hui", due=today)
        self.task("Demain", due=today + timedelta(days=1))

        self.assertEqual(self.titles("late", Week.of(today).slug), ["Hier"])

    @expectedFailure
    def test_semaine_a_venir_sans_retard(self):
        """Un retard à venir ne se sait pas : la rubrique n'apparaît pas."""
        from core.weeks import Week

        today = timezone.localdate()
        self.task("Hier", due=today - timedelta(days=1))

        html = self.html(Week.of(today + timedelta(days=14)).slug)

        self.assertNotIn("week-late", html)
        self.assertNotIn("Hier", html)


class DisplayTests(WeekTasksTestCase):
    @expectedFailure
    def test_projet_et_compte(self):
        self.task("T", completed=at(MONDAY))

        html = self.html()

        self.assertRegex(
            html, r'<h3 id="week-done"[^>]*>Terminées <span[^>]*>\(1\)</span></h3>'
        )
        self.assertIn(">P</span>", html)

    @expectedFailure
    def test_tache_sans_projet(self):
        self.task("T", completed=at(MONDAY))
        Task.objects.update(project=None)

        self.assertEqual(self.titles("done"), ["T"])

    @expectedFailure
    def test_titre_echappe(self):
        self.task("<b>R&D</b>", completed=at(MONDAY))

        self.assertEqual(self.titles("done"), ["&lt;b&gt;R&amp;D&lt;/b&gt;"])

    @expectedFailure
    def test_nombre_de_requetes_constant(self):
        def count() -> int:
            with CaptureQueriesContext(connection) as captured:
                self.html()
            return len(captured)

        self.task("T", created=at(MONDAY), due=MONDAY)
        self.task("U", completed=at(MONDAY))
        before = count()
        for index in range(6):
            self.project = Project.objects.create(name=f"P{index}")
            self.task(f"T{index}", created=at(MONDAY), due=MONDAY)
            self.task(f"U{index}", completed=at(MONDAY))

        self.assertEqual(count(), before)
