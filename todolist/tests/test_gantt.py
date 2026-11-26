"""Tests de la frise de type Gantt des sous-tâches, dans le détail (#168)."""

import re
from datetime import date, datetime

from django.test import SimpleTestCase, TestCase
from django.urls import reverse
from django.utils import timezone

from core.models import Project
from todolist.models import Task

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

    def task(self, title: str, created: date, **fields) -> Task:
        task = Task.objects.create(title=title, project=self.project, **fields)
        Task.objects.filter(pk=task.pk).update(created_at=aware(created))
        return task

    def chart(self):
        from todolist.gantt import gantt_chart

        return gantt_chart(Task.objects.get(pk=self.parent.pk), today=TODAY)


class GanttChartTests(GanttTestCase):
    def test_tache_observee_puis_ses_sous_taches(self):
        """La tâche observée a sa propre barre, ses sous-tâches indentées dessous."""
        rows = self.chart().rows

        self.assertEqual(
            [(row.task.title, row.level) for row in rows],
            [("Parent", 0), ("Enfant", 1), ("Petit-enfant", 2), ("Sans échéance", 1)],
        )
        self.assertEqual((rows[0].start, rows[0].width), (0.0, 100.0))

    def test_axe_de_la_premiere_creation_a_la_derniere_date(self):
        chart = self.chart()

        # Du 1er janvier au 31 mars (échéance du parent) : 89 jours.
        self.assertEqual(
            (chart.start, chart.end), (date(2026, 1, 1), date(2026, 3, 31))
        )
        # Le 1er mars : 59 jours sur 89.
        self.assertEqual(chart.today, 66.3)
        self.assertEqual(chart.parent_due, 100.0)

    def test_position_longueur_et_avancement_d_une_barre(self):
        grandchild = self.chart().rows[2]

        self.assertEqual((grandchild.start, grandchild.width), (33.7, 11.2))
        self.assertEqual(grandchild.progress, 40)
        self.assertFalse(grandchild.open_end)

    def test_barre_ouverte_jusqu_a_aujourd_hui_sans_echeance(self):
        open_row = self.chart().rows[3]

        self.assertTrue(open_row.open_end)
        self.assertEqual(open_row.start + open_row.width, self.chart().today)

    def test_debuts_de_mois(self):
        self.assertEqual(
            [tick.label for tick in self.chart().ticks], ["jan.", "fév.", "mars"]
        )

    def test_tache_terminee_sans_echeance_jusqu_a_sa_completion(self):
        self.open.progress = 100
        self.open.save()
        # `save` réécrit la date de création : remise ensuite, avec la complétion.
        Task.objects.filter(pk=self.open.pk).update(
            created_at=aware(date(2026, 2, 1)), completed_at=aware(date(2026, 2, 10))
        )

        row = self.chart().rows[3]

        self.assertEqual(row.finish, date(2026, 2, 10))
        self.assertFalse(row.open_end)


class GanttAxisTests(GanttTestCase):
    """Axe d'un arbre ancien (#186) : arrêté à sa dernière date quand aujourd'hui est
    loin, avec un repère « Aujourd'hui → » au bord."""

    def chart_on(self, today: date):
        from todolist.gantt import gantt_chart

        return gantt_chart(Task.objects.get(pk=self.parent.pk), today=today)

    def close_open_task(self):
        Task.objects.filter(pk=self.open.pk).update(due_date=date(2026, 2, 20))

    def test_axe_arrete_a_la_derniere_date_quand_aujourd_hui_est_loin(self):
        self.close_open_task()

        chart = self.chart_on(date(2026, 11, 1))

        self.assertEqual(chart.end, date(2026, 3, 31))
        self.assertIsNone(chart.today)
        self.assertTrue(chart.today_beyond)
        self.assertEqual(chart.parent_due, 100.0)

    def test_axe_jusqu_a_aujourd_hui_quand_il_est_proche(self):
        self.close_open_task()

        chart = self.chart_on(date(2026, 4, 10))

        self.assertEqual(chart.end, date(2026, 4, 10))
        self.assertEqual(chart.today, 100.0)
        self.assertFalse(chart.today_beyond)

    def test_tache_en_cours_sans_echeance_garde_aujourd_hui(self):
        """Sa barre va jusqu'à aujourd'hui : l'axe aussi, même loin."""
        chart = self.chart_on(date(2026, 11, 1))

        self.assertEqual(chart.end, date(2026, 11, 1))
        self.assertFalse(chart.today_beyond)


class GanttTicksTests(SimpleTestCase):
    """Repères de mois espacés quand la place manque (#185) : un repère sur trois,
    six ou douze selon la largeur de la frise (requêtes de conteneur)."""

    def ticks(self, start: date, end: date):
        from todolist.gantt import month_ticks

        length = (end - start).days
        return month_ticks(start, end, lambda day: (day - start).days / length * 100)

    def test_axe_court_tous_les_mois_toujours(self):
        ticks = self.ticks(date(2026, 1, 1), date(2026, 3, 31))

        self.assertEqual({tick.visibility for tick in ticks}, {""})

    def test_axe_long_mois_espaces_quand_la_place_manque(self):
        ticks = {
            tick.label: tick.visibility
            for tick in self.ticks(date(2025, 1, 1), date(2026, 12, 31))
        }

        # Plusieurs années : janvier porte l'année, toujours affichée.
        self.assertEqual(ticks["2025"], "")
        self.assertEqual(ticks["2026"], "")
        # Les trimestres d'abord, puis les autres mois sur une frise large.
        self.assertEqual(ticks["avr."], "hidden @min-[32rem]:block")
        self.assertTrue(ticks["fév."].startswith("hidden"))
        visible_from = [
            "",
            "hidden @min-[20rem]:block",
            "hidden @min-[32rem]:block",
            "hidden @min-[48rem]:block",
            "hidden",
        ]
        self.assertLess(
            visible_from.index(ticks["juil."]), visible_from.index(ticks["fév."])
        )


class GanttPageTests(GanttTestCase):
    def html(self, task: Task) -> str:
        return self.client.get(
            reverse("todolist:task_detail", args=[task.pk])
        ).content.decode()

    def test_textes_masques_dans_le_cadre_de_la_frise(self):
        """`sr-only` est en position absolue : sans cadre positionné, une longue frise
        ajoute une seconde barre de défilement à la page (#205)."""
        html = self.html(self.parent)

        self.assertIn('<figure aria-labelledby="gantt-title" class="relative', html)

    def test_frise_dans_le_detail_d_un_parent(self):
        html = self.html(self.parent)

        figure = re.search(
            r'<figure aria-labelledby="gantt-title".*?</figure>', html, re.DOTALL
        )
        assert figure is not None
        self.assertEqual(figure.group().count("data-gantt-row"), 4)
        self.assertIn("left-(--start) w-(--width)", figure.group())
        # La page utilise la vraie date du jour : seules les variables sont vérifiées.
        self.assertRegex(figure.group(), r'style="--start: [\d.]+%; --width: [\d.]+%;')
        self.assertRegex(figure.group(), r"aria-label=\"Aujourd(&#x27;|')hui\"")
        self.assertIn(
            'aria-label="Échéance de la tâche : 31 mars 2026"', figure.group()
        )
        # La colonne des noms ne prend jamais plus d'un tiers environ (#185).
        self.assertIn("grid-cols-[min(14rem,35%)_1fr]", figure.group())
        self.assertIn("@container", figure.group())

    def test_texte_de_chaque_barre_pour_les_lecteurs_d_ecran(self):
        html = self.html(self.parent)

        self.assertIn("du 31 janvier 2026 au 10 février 2026, 40 %", html)
        self.assertIn("depuis le 1er février 2026, sans échéance, 0 %", html)

    def test_aujourd_hui_au_bord_d_un_arbre_ancien(self):
        """Les dates des tâches de test sont passées : sans la tâche en cours sans
        échéance, l'axe s'arrête avant aujourd'hui (#186)."""
        self.open.delete()

        html = self.html(self.parent)

        self.assertRegex(html, r"Aujourd(&#x27;|')hui →")
        self.assertNotRegex(html, r"aria-label=\"Aujourd(&#x27;|')hui\"")

    def test_pas_de_frise_sans_sous_tache(self):
        html = self.html(self.grandchild)

        self.assertNotIn("gantt-title", html)
