"""Tests de la frise de type Gantt des sous-tâches, dans le détail (#168)."""

import re
import unittest
from datetime import date, datetime

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from core.models import Project
from todolist.models import Todo

TODAY = date(2026, 3, 1)


def aware(day: date) -> datetime:
    return timezone.make_aware(datetime(day.year, day.month, day.day, 12, 0))


class GanttTestCase(TestCase):
    def setUp(self):
        self.project = Project.objects.create(name="P")
        self.parent = self.task("Parent", date(2026, 1, 1), due_date=date(2026, 3, 31))
        self.child = self.task(
            "Enfant", date(2026, 1, 1), parent=self.parent, due_date=date(2026, 2, 15)
        )
        self.grandchild = self.task(
            "Petit-enfant",
            date(2026, 1, 31),
            parent=self.child,
            due_date=date(2026, 2, 10),
            progress=40,
        )
        self.open = self.task("Sans échéance", date(2026, 2, 1), parent=self.parent)

    def task(self, title: str, created: date, **fields) -> Todo:
        task = Todo.objects.create(title=title, project=self.project, **fields)
        Todo.objects.filter(pk=task.pk).update(created_at=aware(created))
        return task

    def chart(self):
        from todolist.gantt import gantt_chart

        return gantt_chart(Todo.objects.get(pk=self.parent.pk), today=TODAY)


class GanttChartTests(GanttTestCase):
    @unittest.expectedFailure
    def test_lignes_dans_l_ordre_du_tableau(self):
        rows = self.chart().rows

        self.assertEqual(
            [(row.task.title, row.level) for row in rows],
            [("Enfant", 0), ("Petit-enfant", 1), ("Sans échéance", 0)],
        )

    @unittest.expectedFailure
    def test_axe_de_la_premiere_creation_a_la_derniere_date(self):
        chart = self.chart()

        # Du 1er janvier au 31 mars (échéance du parent) : 89 jours.
        self.assertEqual(
            (chart.start, chart.end), (date(2026, 1, 1), date(2026, 3, 31))
        )
        # Le 1er mars : 59 jours sur 89.
        self.assertEqual(chart.today, 66.3)
        self.assertEqual(chart.parent_due, 100.0)

    @unittest.expectedFailure
    def test_position_longueur_et_avancement_d_une_barre(self):
        grandchild = self.chart().rows[1]

        self.assertEqual((grandchild.start, grandchild.width), (33.7, 11.2))
        self.assertEqual(grandchild.progress, 40)
        self.assertFalse(grandchild.open_end)

    @unittest.expectedFailure
    def test_barre_ouverte_jusqu_a_aujourd_hui_sans_echeance(self):
        open_row = self.chart().rows[2]

        self.assertTrue(open_row.open_end)
        self.assertEqual(open_row.start + open_row.width, self.chart().today)

    @unittest.expectedFailure
    def test_debuts_de_mois(self):
        self.assertEqual(
            [label for label, _ in self.chart().ticks], ["janv.", "févr.", "mars"]
        )


class GanttPageTests(GanttTestCase):
    def html(self, todo: Todo) -> str:
        return self.client.get(
            reverse("todolist:todo_detail", args=[todo.pk])
        ).content.decode()

    @unittest.expectedFailure
    def test_frise_dans_le_detail_d_un_parent(self):
        html = self.html(self.parent)

        figure = re.search(
            r'<figure aria-labelledby="gantt-title".*?</figure>', html, re.DOTALL
        )
        assert figure is not None
        self.assertEqual(figure.group().count("data-gantt-row"), 3)
        self.assertIn("left-(--start) w-(--width)", figure.group())
        # La page utilise la vraie date du jour : seules les variables sont vérifiées.
        self.assertRegex(figure.group(), r'style="--start: [\d.]+%; --width: [\d.]+%;')
        self.assertIn('aria-label="Aujourd&#x27;hui"', figure.group())
        self.assertIn('aria-label="Échéance de la tâche"', figure.group())

    @unittest.expectedFailure
    def test_texte_de_chaque_barre_pour_les_lecteurs_d_ecran(self):
        html = self.html(self.parent)

        self.assertIn("du 31 janvier 2026 au 10 février 2026, 40 %", html)
        self.assertIn("depuis le 1 février 2026, sans échéance, 0 %", html)

    def test_pas_de_frise_sans_sous_tache(self):
        html = self.html(self.grandchild)

        self.assertNotIn("gantt-title", html)
