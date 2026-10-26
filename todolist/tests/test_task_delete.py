"""Suppression d'une tâche parente : ses sous-tâches sont annoncées (#223).

Décision du 2026-10-26 : avertir, puis supprimer la tâche avec ses sous-tâches.
Un arbre qui contient une tâche issue d'une note est écarté, et la page le dit :
bouton, confirmation et message (#290).
"""

import re
from html import unescape

from django.contrib.messages import get_messages
from django.test import TestCase
from django.urls import reverse

from core.models import Project
from note_taking.models import Note
from note_taking.services import process_note_parts
from todolist.models import Todo

# La confirmation est une popover HTML native, ouverte par le bouton de l'en-tête.
CONFIRM_REGEX = re.compile(
    r'<div id="delete-confirm" popover[^>]*>\s*<p[^>]*>(?P<message>[^<]*)</p>'
)


class DeleteTestCase(TestCase):
    def confirm(self, task: Todo) -> str:
        html = self.client.get(
            reverse("todolist:todo_detail", args=[task.pk])
        ).content.decode()
        match = CONFIRM_REGEX.search(html)
        assert match is not None
        return unescape(match.group("message"))

    def delete(self, task: Todo) -> list[str]:
        response = self.client.post(reverse("todolist:todo_delete", args=[task.pk]))
        return [str(m) for m in get_messages(response.wsgi_request)]


class ParentDeleteTests(DeleteTestCase):
    def setUp(self):
        project = Project.objects.create(name="P")
        self.parent = Todo.objects.create(title="Parent", project=project)
        self.child = Todo.objects.create(
            title="Enfant", project=project, parent=self.parent
        )
        self.project = project

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

    def test_sous_taches_supprimees_avec_la_tache(self):
        self.add_grandchildren()

        self.delete(self.parent)

        self.assertFalse(Todo.objects.exists())

    def test_bouton_supprimer(self):
        response = self.client.get(
            reverse("todolist:todo_detail", args=[self.parent.pk])
        )

        self.assertContains(response, "Supprimer la tâche")
        self.assertNotContains(response, "Écarter la tâche")

    def test_message_de_suppression(self):
        self.assertEqual(
            self.delete(self.parent),
            ["La tâche « Parent » et sa sous-tâche sont supprimées."],
        )


class DismissTests(DeleteTestCase):
    """Une tâche issue d'une note, ou un arbre qui en contient une : écartée."""

    def setUp(self):
        note = Note.objects.create(date="2025-11-24", body="# P\n### TODO\n- A\n  - B")
        process_note_parts(note)
        self.a = Todo.objects.get(title="A")
        self.b = Todo.objects.get(title="B")

    def detail(self, task: Todo) -> str:
        return self.client.get(
            reverse("todolist:todo_detail", args=[task.pk])
        ).content.decode()

    def test_bouton_ecarter(self):
        html = self.detail(self.a)

        self.assertIn("Écarter la tâche", html)
        self.assertNotIn("Supprimer la tâche", html)

    def test_confirmation(self):
        self.assertEqual(
            self.confirm(self.a),
            "Écarter la tâche « A » et sa sous-tâche ? La section « Écartées » "
            "de la liste des tâches permet de revenir en arrière.",
        )

    def test_message(self):
        self.assertEqual(self.delete(self.b), ["La tâche « B » est écartée."])

    def test_message_avec_sous_taches(self):
        self.assertEqual(
            self.delete(self.a), ["La tâche « A » et sa sous-tâche sont écartées."]
        )

    def test_parent_saisi_a_la_main(self):
        parent = Todo.objects.create(title="Parent", project=self.a.project)
        Todo.objects.filter(pk=self.a.pk).update(parent=parent)

        self.assertIn("Écarter la tâche", self.detail(parent))
        self.assertEqual(
            self.delete(parent),
            ["La tâche « Parent » et ses 2 sous-tâches sont écartées."],
        )
