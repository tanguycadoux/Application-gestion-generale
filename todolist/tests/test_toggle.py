"""Tests de la vue de complétion d'une TODO (case à cocher de la liste)."""

import json

from django.test import TestCase
from django.urls import reverse

from core.models import Project
from todolist.models import Todo


class ToggleTodoTests(TestCase):
    def setUp(self):
        self.parent = Todo.objects.create(
            project=Project.objects.get_or_create(name="P")[0], title="Parent"
        )
        self.child = Todo.objects.create(
            project=Project.objects.get_or_create(name="P")[0],
            title="Enfant",
            parent=self.parent,
        )
        self.grandchild = Todo.objects.create(
            project=Project.objects.get_or_create(name="P")[0],
            title="Petit-enfant",
            parent=self.child,
        )

    def toggle(self, todo: Todo, **data):
        return self.client.post(
            reverse("todolist:todo_toggle", args=[todo.pk]),
            json.dumps(data),
            content_type="application/json",
        )

    def completed(self, *todos: Todo) -> list[bool]:
        return [Todo.objects.get(pk=todo.pk).completed for todo in todos]

    def test_completer_une_todo_sans_sous_taches(self):
        response = self.toggle(self.grandchild, completed=True)

        self.assertEqual(response.json()["status"], "ok")
        self.assertEqual(self.completed(self.grandchild), [True])

    def test_confirmation_demandee_si_sous_taches_non_terminees(self):
        response = self.toggle(self.parent, completed=True)

        self.assertEqual(response.json()["status"], "needs_confirmation")
        self.assertEqual(response.json()["children_count"], 1)
        self.assertEqual(
            self.completed(self.parent, self.child, self.grandchild),
            [False, False, False],
        )

    def test_forcer_complete_toutes_les_sous_taches(self):
        response = self.toggle(self.parent, completed=True, force=True)

        self.assertEqual(response.json()["status"], "ok")
        self.assertEqual(
            self.completed(self.parent, self.child, self.grandchild),
            [True, True, True],
        )

    def test_decocher_ne_touche_pas_les_sous_taches(self):
        self.toggle(self.parent, completed=True, force=True)

        self.toggle(self.parent, completed=False)

        self.assertEqual(
            self.completed(self.parent, self.child, self.grandchild),
            [False, True, True],
        )

    def test_methode_get_refusee(self):
        response = self.client.get(
            reverse("todolist:todo_toggle", args=[self.parent.pk])
        )

        self.assertEqual(response.status_code, 405)

    def test_ids_des_todos_modifiees(self):
        response = self.toggle(self.parent, completed=True, force=True)

        self.assertEqual(
            sorted(response.json()["toggled_ids"]),
            sorted([self.parent.pk, self.child.pk, self.grandchild.pk]),
        )

    def test_todo_inexistante(self):
        response = self.toggle(Todo(pk=999), completed=True)

        self.assertEqual(response.status_code, 404)

    def test_corps_invalide(self):
        response = self.client.post(
            reverse("todolist:todo_toggle", args=[self.parent.pk]),
            "pas du json",
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 400)

    def test_json_qui_n_est_pas_un_objet(self):
        response = self.client.post(
            reverse("todolist:todo_toggle", args=[self.parent.pk]),
            "[]",
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 400)
