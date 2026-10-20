"""Tests des incohérences signalées plutôt qu'empêchées (#165)."""

from datetime import date

from django.test import TestCase
from django.urls import reverse

from core.models import Project
from todolist.models import Todo


class IncoherenceTestCase(TestCase):
    def setUp(self):
        self.project = Project.objects.create(name="P")
        self.other_project = Project.objects.create(name="Autre")
        self.parent = self.task("Parent", due_date=date(2025, 12, 1))
        self.child = self.task(
            "Enfant", parent=self.parent, due_date=date(2025, 11, 20)
        )

    def task(self, title: str, **fields) -> Todo:
        fields.setdefault("project", self.project)
        return Todo.objects.create(title=title, **fields)

    def messages(self, todo: Todo) -> list[tuple[str, int]]:
        todo = Todo.objects.get(pk=todo.pk)
        return [(i.message, i.task.pk) for i in todo.incoherences()]


class DueDateTests(IncoherenceTestCase):
    def test_aucune_incoherence(self):
        self.assertEqual(self.messages(self.parent), [])
        self.assertEqual(self.messages(self.child), [])

    def test_echeance_d_un_enfant_apres_celle_du_parent(self):
        self.child.due_date = date(2025, 12, 5)
        self.child.save()

        self.assertEqual(
            self.messages(self.parent),
            [
                (
                    "L'échéance de la sous-tâche « Enfant » (5 décembre 2025) "
                    "est après celle-ci (1 décembre 2025).",
                    self.child.pk,
                )
            ],
        )
        self.assertEqual(
            self.messages(self.child),
            [
                (
                    "Son échéance (5 décembre 2025) est après celle de la tâche "
                    "parente « Parent » (1 décembre 2025).",
                    self.parent.pk,
                )
            ],
        )

    def test_echeance_absente_sans_incoherence(self):
        self.task("Sans échéance", parent=self.parent)
        self.parent.due_date = None
        self.parent.save()

        self.assertEqual(self.messages(self.parent), [])


class ProjectTests(IncoherenceTestCase):
    def test_projet_different_de_celui_du_parent(self):
        self.child.project = self.other_project
        self.child.save()

        self.assertEqual(
            self.messages(self.parent),
            [
                (
                    "La sous-tâche « Enfant » a un autre projet (Autre).",
                    self.child.pk,
                )
            ],
        )
        self.assertEqual(
            self.messages(self.child),
            [
                (
                    "Son projet (Autre) diffère de celui de la tâche parente "
                    "« Parent » (P).",
                    self.parent.pk,
                )
            ],
        )


class DoneTests(IncoherenceTestCase):
    def test_parent_termine_avec_un_enfant_en_cours(self):
        self.parent.done = True
        self.parent.save()

        self.assertEqual(
            self.messages(self.parent),
            [
                (
                    "Elle est terminée alors que la sous-tâche « Enfant » ne l'est pas.",
                    self.child.pk,
                )
            ],
        )
        self.assertEqual(
            self.messages(self.child),
            [
                (
                    "Elle n'est pas terminée alors que la tâche parente « Parent » "
                    "l'est.",
                    self.parent.pk,
                )
            ],
        )


class DisplayTests(IncoherenceTestCase):
    def setUp(self):
        super().setUp()
        self.child.project = self.other_project
        self.child.save()

    def test_encadre_dans_le_detail(self):
        html = self.client.get(
            reverse("todolist:todo_detail", args=[self.parent.pk])
        ).content.decode()

        self.assertIn('<aside aria-labelledby="incoherences-title"', html)
        self.assertIn('<h2 id="incoherences-title"', html)
        self.assertIn("La sous-tâche « Enfant » a un autre projet (Autre).", html)
        self.assertIn(
            f'href="{reverse("todolist:todo_detail", args=[self.child.pk])}"', html
        )

    def test_pas_d_encadre_sans_incoherence(self):
        task = self.task("Seule")

        html = self.client.get(
            reverse("todolist:todo_detail", args=[task.pk])
        ).content.decode()

        self.assertNotIn("incoherences-title", html)

    def test_indicateur_dans_la_liste(self):
        self.task("Seule")

        html = self.client.get(reverse("todolist:todo_list")).content.decode()

        # Le parent et l'enfant, pas la tâche « Seule ».
        self.assertEqual(html.count('aria-label="Incohérences à corriger"'), 2)
