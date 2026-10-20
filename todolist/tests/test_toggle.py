"""Tests de la vue de complétion d'une tâche (case à cocher de la liste)."""

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

    def test_methode_get_refusee(self):
        response = self.client.get(
            reverse("todolist:todo_toggle", args=[self.parent.pk])
        )

        self.assertEqual(response.status_code, 405)

    def test_ids_de_la_tache_et_de_ses_ancetres_modifies(self):
        """La tâche cochée et ses ancêtres dont l'avancement change (#164)."""
        response = self.toggle(self.grandchild, completed=True)

        self.assertEqual(
            response.json()["toggled_ids"],
            [self.grandchild.pk, self.child.pk, self.parent.pk],
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
