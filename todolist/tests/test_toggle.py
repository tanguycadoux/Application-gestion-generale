"""Tests de la vue de complétion d'une tâche (case à cocher de la liste)."""

import json

from django.test import TestCase
from django.urls import reverse

from core.models import Project
from todolist.models import Task


class ToggleTaskTests(TestCase):
    def setUp(self):
        self.parent = Task.objects.create(
            project=Project.objects.get_or_create(name="P")[0], title="Parent"
        )
        self.child = Task.objects.create(
            project=Project.objects.get_or_create(name="P")[0],
            title="Enfant",
            parent=self.parent,
        )
        self.grandchild = Task.objects.create(
            project=Project.objects.get_or_create(name="P")[0],
            title="Petit-enfant",
            parent=self.child,
        )

    def toggle(self, task: Task, **data):
        return self.client.post(
            reverse("todolist:task_toggle", args=[task.pk]),
            json.dumps(data),
            content_type="application/json",
        )

    def completed(self, *tasks: Task) -> list[bool]:
        return [Task.objects.get(pk=task.pk).completed for task in tasks]

    def test_methode_get_refusee(self):
        response = self.client.get(
            reverse("todolist:task_toggle", args=[self.parent.pk])
        )

        self.assertEqual(response.status_code, 405)

    def test_ids_de_la_tache_et_de_ses_ancetres_modifies(self):
        """La tâche cochée et ses ancêtres dont l'avancement change (#164)."""
        response = self.toggle(self.grandchild, completed=True)

        self.assertEqual(
            response.json()["toggled_ids"],
            [self.grandchild.pk, self.child.pk, self.parent.pk],
        )

    def test_tache_inexistante(self):
        response = self.toggle(Task(pk=999), completed=True)

        self.assertEqual(response.status_code, 404)

    def test_corps_invalide(self):
        response = self.client.post(
            reverse("todolist:task_toggle", args=[self.parent.pk]),
            "pas du json",
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 400)

    def test_json_qui_n_est_pas_un_objet(self):
        response = self.client.post(
            reverse("todolist:task_toggle", args=[self.parent.pk]),
            "[]",
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 400)


class UncheckRestoresProgressTests(TestCase):
    """Décocher rend l'avancement d'avant la coche (#237)."""

    def setUp(self):
        self.task = Task.objects.create(
            project=Project.objects.get_or_create(name="P")[0],
            title="Tâche",
            progress=60,
        )

    def toggle(self, completed: bool):
        return self.client.post(
            reverse("todolist:task_toggle", args=[self.task.pk]),
            json.dumps({"completed": completed}),
            content_type="application/json",
        )

    def progress(self) -> int:
        return Task.objects.get(pk=self.task.pk).progress

    def test_cocher_puis_decocher(self):
        self.toggle(True)
        self.toggle(False)

        self.assertEqual(self.progress(), 60)

    def test_avancement_porte_a_100_dans_le_formulaire_puis_decoche(self):
        self.task.progress = 100
        self.task.save()
        self.toggle(False)

        self.assertEqual(self.progress(), 60)

    def test_creee_terminee_puis_decochee(self):
        self.task = Task.objects.create(
            project=Project.objects.get(name="P"), title="Finie", progress=100
        )
        self.toggle(False)

        self.assertEqual(self.progress(), 0)

    def test_recocher_retient_le_dernier_avancement(self):
        self.toggle(True)
        self.toggle(False)
        self.task.refresh_from_db()
        self.task.progress = 30
        self.task.save()
        self.toggle(True)
        self.toggle(False)

        self.assertEqual(self.progress(), 30)
