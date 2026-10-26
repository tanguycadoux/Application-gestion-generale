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


class UncheckRestoresProgressTests(TestCase):
    """Décocher rend l'avancement d'avant la coche (#237)."""

    def setUp(self):
        self.todo = Todo.objects.create(
            project=Project.objects.get_or_create(name="P")[0],
            title="Tâche",
            progress=60,
        )

    def toggle(self, completed: bool):
        return self.client.post(
            reverse("todolist:todo_toggle", args=[self.todo.pk]),
            json.dumps({"completed": completed}),
            content_type="application/json",
        )

    def progress(self) -> int:
        return Todo.objects.get(pk=self.todo.pk).progress

    def test_cocher_puis_decocher(self):
        self.toggle(True)
        self.toggle(False)

        self.assertEqual(self.progress(), 60)

    def test_avancement_porte_a_100_dans_le_formulaire_puis_decoche(self):
        self.todo.progress = 100
        self.todo.save()
        self.toggle(False)

        self.assertEqual(self.progress(), 60)

    def test_creee_terminee_puis_decochee(self):
        self.todo = Todo.objects.create(
            project=Project.objects.get(name="P"), title="Finie", progress=100
        )
        self.toggle(False)

        self.assertEqual(self.progress(), 0)

    def test_recocher_retient_le_dernier_avancement(self):
        self.toggle(True)
        self.toggle(False)
        self.todo.refresh_from_db()
        self.todo.progress = 30
        self.todo.save()
        self.toggle(True)
        self.toggle(False)

        self.assertEqual(self.progress(), 30)
