"""Tests de la vue de complétion d'une TODO (case à cocher de la liste)."""

import json
import unittest

from django.test import TestCase
from django.urls import reverse

from todolist.models import Todo


class ToggleTodoTests(TestCase):
    def setUp(self):
        self.parent = Todo.objects.create(title="Parent")
        self.child = Todo.objects.create(title="Enfant", parent=self.parent)
        self.grandchild = Todo.objects.create(title="Petit-enfant", parent=self.child)

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

    @unittest.expectedFailure
    def test_ids_des_todos_modifiees(self):
        """#15 : toggled_ids est toujours vide."""
        response = self.toggle(self.parent, completed=True, force=True)

        self.assertEqual(
            sorted(response.json()["toggled_ids"]),
            sorted([self.parent.pk, self.child.pk, self.grandchild.pk]),
        )

    @unittest.expectedFailure
    def test_todo_inexistante(self):
        """#15 : erreur 500 au lieu de 404."""
        response = self.toggle(Todo(pk=999), completed=True)

        self.assertEqual(response.status_code, 404)

    @unittest.expectedFailure
    def test_corps_invalide(self):
        """#15 : erreur 500 au lieu de 400."""
        response = self.client.post(
            reverse("todolist:todo_toggle", args=[self.parent.pk]),
            "pas du json",
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 400)
