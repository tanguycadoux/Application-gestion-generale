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
            None: "bg-neutral-95",
            "normal": "bg-neutral-95",
            "soon": "bg-primary-95",
            "today": "bg-primary-95",
            "overdue": "bg-alert-90",
        }
        for status in STATUSES:
            with self.subTest(status=status):
                classes = render("{{ status|todo_card_classes }}", status).split()

                self.assertIn("grid-cols-subgrid", classes)
                self.assertIn(expected[status], classes)

    def test_contour_pour_aujourd_hui_et_en_retard(self):
        for status, border in (("today", "primary-60"), ("overdue", "alert-60")):
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
            "soon": "text-primary-40",
            "today": "text-primary-40",
            "overdue": "text-alert-40",
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
            None: "bg-neutral-95",
            "normal": "bg-neutral-95",
            "soon": "bg-primary-95",
            "today": "bg-primary-95",
            "overdue": "bg-alert-90",
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

    def test_liste_sans_classes_maison(self):
        html = self.client.get(reverse("todolist:todo_list")).content.decode()

        self.assertIn("bg-alert-90", html)
        self.assertIn("after:border-alert-60", html)
        for legacy in ("todo-list__", "todo-line-item", "todo--", "h2-like"):
            with self.subTest(legacy=legacy):
                self.assertNotIn(legacy, html)

    def test_detail_sans_classes_maison(self):
        response = self.client.get(
            reverse("todolist:todo_detail", args=[self.parent.pk])
        )
        html = response.content.decode()

        self.assertIn("not-first:border-t", html)
        self.assertNotIn("todo-list__", html)
        self.assertNotIn("todo-line-item", html)

    def test_feuille_de_style_de_l_app_retiree(self):
        html = self.client.get(reverse("todolist:todo_list")).content.decode()

        self.assertNotIn("todolist/style.css", html)
