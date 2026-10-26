"""Suppression d'une tâche parente : ses sous-tâches sont annoncées (#223).

Décision du 2026-10-26 : avertir, puis supprimer la tâche avec ses sous-tâches.
"""

import re

from django.contrib.messages import get_messages
from django.test import TestCase
from django.urls import reverse

from core.models import Project
from todolist.models import Todo

CONFIRM_REGEX = re.compile(r'data-confirm="(?P<message>[^"]*)"')


class ParentDeleteTests(TestCase):
    def setUp(self):
        project = Project.objects.create(name="P")
        self.parent = Todo.objects.create(title="Parent", project=project)
        self.child = Todo.objects.create(
            title="Enfant", project=project, parent=self.parent
        )
        self.project = project

    def confirm(self, task: Todo) -> str:
        html = self.client.get(
            reverse("todolist:todo_detail", args=[task.pk])
        ).content.decode()
        match = CONFIRM_REGEX.search(html)
        assert match is not None
        return match.group("message")

    def delete(self, task: Todo) -> list[str]:
        response = self.client.post(reverse("todolist:todo_delete", args=[task.pk]))
        return [str(m) for m in get_messages(response.wsgi_request)]

    def add_grandchildren(self):
        Todo.objects.create(title="Enfant 2", project=self.project, parent=self.parent)
        Todo.objects.create(
            title="Petit-enfant", project=self.project, parent=self.child
        )

    def test_confirmation_annonce_les_sous_taches_descendants_compris(self):
        self.add_grandchildren()

        self.assertEqual(
            self.confirm(self.parent),
            "Supprimer définitivement la tâche « Parent » et ses 3 sous-tâches ?",
        )

    def test_confirmation_une_seule_sous_tache(self):
        self.assertEqual(
            self.confirm(self.parent),
            "Supprimer définitivement la tâche « Parent » et sa sous-tâche ?",
        )

    def test_confirmation_sans_sous_tache_inchangee(self):
        self.assertEqual(
            self.confirm(self.child),
            "Supprimer définitivement la tâche « Enfant » ?",
        )

    def test_message_annonce_les_sous_taches_supprimees(self):
        self.add_grandchildren()

        messages = self.delete(self.parent)

        self.assertEqual(
            messages, ["La tâche « Parent » et ses 3 sous-tâches ont été supprimées."]
        )
        self.assertFalse(Todo.objects.exists())

    def test_message_sans_sous_tache_inchange(self):
        self.assertEqual(
            self.delete(self.child), ["La tâche « Enfant » a été supprimée."]
        )
