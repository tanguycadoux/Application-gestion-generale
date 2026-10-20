"""Tests du style des TODO selon leur échéance (classes Tailwind, #79)."""

from datetime import date, timedelta

from django.template import Context, Template
from django.test import SimpleTestCase, TestCase
from django.urls import reverse

from todolist.models import Todo

STATUSES = (None, "normal", "soon", "today", "overdue")


def render(source: str, status: str | None) -> str:
    template = Template("{% load todo_ui %}" + source)
    return template.render(Context({"status": status}))


class DueClassesTests(SimpleTestCase):
    def test_carte_principale(self):
        expected = {
            None: "bg-slate-100",
            "normal": "bg-slate-100",
            "soon": "bg-blue-50",
            "today": "bg-blue-50",
            "overdue": "bg-red-200",
        }
        for status in STATUSES:
            with self.subTest(status=status):
                classes = render("{{ status|todo_card_classes }}", status).split()

                self.assertIn("grid-cols-subgrid", classes)
                self.assertIn(expected[status], classes)

    def test_contour_pour_aujourd_hui_et_en_retard(self):
        for status, border in (("today", "blue-500"), ("overdue", "red-500")):
            with self.subTest(status=status):
                classes = render("{{ status|todo_card_classes }}", status).split()

                self.assertIn(f"after:border-{border}", classes)
                self.assertIn("after:border-[.2rem]", classes)

        for status in (None, "normal", "soon"):
            with self.subTest(status=status):
                html = render("{{ status|todo_card_classes }}", status)

                self.assertNotIn("after:", html)

    def test_ligne_en_gras_et_en_couleur_si_echeance_proche(self):
        expected = {
            "soon": "text-blue-800",
            "today": "text-blue-800",
            "overdue": "text-red-800",
        }
        for status in STATUSES:
            with self.subTest(status=status):
                classes = render("{{ status|todo_line_classes }}", status).split()

                self.assertIn("grid-cols-[1fr_auto]", classes)
                if status in expected:
                    self.assertIn(expected[status], classes)
                    self.assertIn("font-semibold", classes)
                else:
                    self.assertNotIn("font-semibold", classes)

    def test_sous_tache(self):
        expected = {
            None: "bg-slate-100",
            "normal": "bg-slate-100",
            "soon": "bg-blue-50",
            "today": "bg-blue-50",
            "overdue": "bg-red-200",
        }
        for status in STATUSES:
            with self.subTest(status=status):
                classes = render("{{ status|todo_child_classes }}", status).split()

                self.assertIn("not-first:border-t", classes)
                self.assertIn(expected[status], classes)


class TodoPagesTests(TestCase):
    def setUp(self):
        yesterday = date.today() - timedelta(days=1)
        self.parent = Todo.objects.create(title="Parent", due_date=yesterday)
        self.child = Todo.objects.create(
            title="Enfant", parent=self.parent, due_date=yesterday
        )

    def test_liste_avec_les_classes_d_echeance(self):
        html = self.client.get(reverse("todolist:todo_list")).content.decode()

        self.assertIn("bg-red-200", html)
        self.assertIn("after:border-red-500", html)

    def test_detail_avec_les_sous_taches_bordees(self):
        response = self.client.get(
            reverse("todolist:todo_detail", args=[self.parent.pk])
        )
        html = response.content.decode()

        self.assertIn("not-first:border-t", html)
