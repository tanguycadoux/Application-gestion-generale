"""Tests de la liste des tâches en tableau arborescent (#166)."""

import re
import unittest
from datetime import timedelta

from django.test import SimpleTestCase, TestCase
from django.urls import reverse
from django.utils import timezone

from core.models import Project
from todolist.models import Todo
from todolist.templatetags.todo_ui import progress_classes

TODAY = timezone.localdate()


def days(n: int):
    return TODAY + timedelta(days=n)


class RemainingTests(SimpleTestCase):
    def remaining(self, offset: int | None, done: bool = False) -> tuple[str, str]:
        from todolist.templatetags.todo_ui import remaining_class, remaining_text

        task = Todo(
            title="T", due_date=None if offset is None else days(offset), done=done
        )
        return remaining_text(task), remaining_class(task)

    def test_formats(self):
        cases = {
            0: "aujourd'hui",
            1: "dans 1 j",
            3: "dans 3 j",
            30: "dans 30 j",
            35: "dans 5 sem.",
            120: "dans 4 mois",
            -2: "2 j de retard",
            -35: "5 sem. de retard",
        }
        for offset, text in cases.items():
            with self.subTest(offset=offset):
                self.assertEqual(self.remaining(offset)[0], text)

    def test_couleur_selon_l_urgence(self):
        self.assertEqual(self.remaining(-1)[1], "text-red-800")
        self.assertEqual(self.remaining(0)[1], "text-amber-800")
        self.assertEqual(self.remaining(3)[1], "text-amber-800")
        self.assertEqual(self.remaining(4)[1], "text-slate-600")

    def test_rien_sans_echeance_ou_terminee(self):
        self.assertEqual(self.remaining(None)[0], "")
        self.assertEqual(self.remaining(-5, done=True)[0], "")


class TaskTreeTests(TestCase):
    def setUp(self):
        self.asterics = Project.objects.create(name="ASTERICS", color="teal")
        self.primager = Project.objects.create(name="PRIMAger", color="purple")

    def task(self, title, project=None, **fields) -> Todo:
        return Todo.objects.create(
            title=title, project=project or self.asterics, **fields
        )

    def test_ordre_des_racines_et_des_freres(self):
        from todolist.tree import task_groups

        late_root = self.task("Racine tardive", due_date=days(20))
        urgent_child_root = self.task(
            "Racine à enfant urgent", self.primager, due_date=days(30)
        )
        self.task(
            "Enfant urgent", self.primager, parent=urgent_child_root, due_date=days(2)
        )
        no_due = self.task("Sans échéance")
        child_b = self.task("B", parent=late_root, due_date=days(10))
        self.task("A sans échéance", parent=late_root)
        self.task("Petit-enfant", parent=child_b, due_date=days(5))

        groups = task_groups(Todo.objects.filter(parent__isnull=True))

        self.assertEqual(
            [group.root.title for group in groups],
            ["Racine à enfant urgent", "Racine tardive", "Sans échéance"],
        )
        self.assertEqual(
            [(row.task.title, row.level) for row in groups[1].rows],
            [
                ("Racine tardive", 0),
                ("B", 1),
                ("Petit-enfant", 2),
                ("A sans échéance", 1),
            ],
        )
        self.assertEqual(groups[2].root, no_due)


class TaskListPageTests(TestCase):
    def setUp(self):
        self.project = Project.objects.create(name="ASTERICS", color="teal")
        self.parent = Todo.objects.create(
            title="Parent", project=self.project, due_date=days(10)
        )
        self.child = Todo.objects.create(
            title="Enfant", project=self.project, parent=self.parent, due_date=days(2)
        )
        self.done_root = Todo.objects.create(
            title="Finie", project=self.project, progress=100
        )

    def html(self) -> str:
        return self.client.get(reverse("todolist:todo_list")).content.decode()

    def test_tableau_avec_un_groupe_par_racine(self):
        html = self.html()
        table = html[html.index("<table") : html.index("</table>")]

        self.assertEqual(table.count("<tbody"), 1)
        self.assertRegex(
            table, r'<th scope="rowgroup" colspan="5"[^>]*>\s*<span class="inline-flex'
        )
        self.assertIn("bg-teal-500", table)
        self.assertLess(table.index(">Parent<"), table.index(">Enfant<"))

    def test_ligne_d_une_tache(self):
        html = self.html()
        row = re.search(r"<tr[^>]*>(?:(?!</tr>).)*>Enfant<.*?</tr>", html, re.DOTALL)
        assert row is not None
        row_html = row.group()

        self.assertIn('class="todo-toggle"', row_html)
        self.assertIn(
            f'href="{reverse("todolist:todo_detail", args=[self.child.pk])}"', row_html
        )
        self.assertIn("pl-6", row_html)
        self.assertIn("dans 2 j", row_html)
        self.assertIn(f'datetime="{days(2).isoformat()}"', row_html)

    def test_terminees_dans_une_section_repliee(self):
        html = self.html()

        self.assertRegex(html, r"<details>\s*<summary[^>]*>.*Terminées \(1\)")
        self.assertLess(html.index("<details>"), html.index(">Finie<"))

    def test_meme_tableau_dans_le_detail_d_un_parent(self):
        html = self.client.get(
            reverse("todolist:todo_detail", args=[self.parent.pk])
        ).content.decode()

        section = html[html.index('aria-labelledby="children-title"') :]
        self.assertIn("<table", section)
        self.assertIn(">Enfant<", section)
        self.assertNotIn('scope="rowgroup"', section)


class ProgressBarTests(TestCase):
    """Avancement en barre dans sa colonne (#182)."""

    def setUp(self):
        project = Project.objects.create(name="ASTERICS", color="teal")
        self.parent = Todo.objects.create(title="Parent", project=project)
        self.child = Todo.objects.create(
            title="Enfant", project=project, parent=self.parent, progress=40
        )

    def html(self) -> str:
        return self.client.get(reverse("todolist:todo_list")).content.decode()

    def test_colonne_avancement(self):
        self.assertIn(
            '<th scope="col" class="w-24 p-2 font-medium">Avancement</th>', self.html()
        )

    def test_barre_de_chaque_tache(self):
        html = self.html()

        self.assertRegex(
            html, r'<progress value="40" max="100"[^>]*aria-label="Avancement : 40 %"'
        )
        self.assertRegex(
            html,
            r'<progress value="40" max="100"[^>]*aria-label="Avancement : 40 %"[^>]*>',
        )
        # Le parent : moyenne de son unique enfant.
        self.assertEqual(html.count('aria-label="Avancement : 40 %"'), 2)

    def test_barre_seulement_sans_pourcentage_a_cote_du_nom(self):
        self.assertNotIn("(40 %)", self.html())

    @unittest.expectedFailure
    def test_terminee_en_vert(self):
        self.child.progress = 100
        self.child.save()

        classes = progress_classes(Todo.objects.get(pk=self.child.pk))

        self.assertIn("[&::-webkit-progress-value]:bg-green-500", classes)
        self.assertIn("bg-green-200", classes)

    @unittest.expectedFailure
    def test_couleur_selon_l_echeance_comme_les_toasts(self):
        """Mêmes couleurs que les barres des toasts : info, avertissement, erreur."""
        cases = {
            None: ("blue-400", "blue-100"),
            10: ("blue-400", "blue-100"),
            3: ("amber-400", "amber-100"),
            0: ("amber-400", "amber-100"),
            -1: ("red-400", "red-100"),
        }
        for offset, (fill, track) in cases.items():
            with self.subTest(offset=offset):
                task = Todo(
                    title="T", due_date=None if offset is None else days(offset)
                )
                classes = progress_classes(task)
                self.assertIn(f"[&::-webkit-progress-value]:bg-{fill}", classes)
                self.assertIn(f"[&::-moz-progress-bar]:bg-{fill}", classes)
                self.assertIn(f" bg-{track}", classes)
                self.assertIn(f"[&::-webkit-progress-bar]:bg-{track}", classes)

    @unittest.expectedFailure
    def test_parent_a_valider_selon_son_echeance(self):
        self.parent.due_date = days(-2)
        self.parent.save()
        self.child.progress = 100
        self.child.save()

        parent = Todo.objects.get(pk=self.parent.pk)

        self.assertTrue(parent.to_validate)
        self.assertIn("bg-red-400", progress_classes(parent))
