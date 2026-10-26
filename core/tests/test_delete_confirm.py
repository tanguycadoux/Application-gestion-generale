"""Tests de la suppression : un seul fonctionnement, confirmation par popover (#126).

Comme pour les images : un bouton dans un formulaire POST portant `data-confirm`,
et des vues limitées à POST, sans page de confirmation.
"""

import re

from django.contrib.messages import get_messages
from django.test import TestCase
from django.urls import reverse

from core.models import Project
from core.templatetags.ui import BUTTON_VARIANTS
from note_taking.models import Note
from todolist.models import Todo


def page_header(html: str) -> str:
    match = re.search(r"<header.*?</header>", html, re.DOTALL)
    assert match is not None
    return match.group()


class DeleteFormTestCase(TestCase):
    def assert_delete_form(self, html: str, action: str, message: str):
        header = page_header(html)
        form = re.search(
            rf'<form method="post" action="{re.escape(action)}"'
            r' data-confirm="(?P<message>[^"]*)">(?P<body>.*?)</form>',
            header,
            re.DOTALL,
        )
        assert form is not None, header
        self.assertEqual(form.group("message"), message)
        self.assertIn("csrfmiddlewaretoken", form.group("body"))
        self.assertIn(
            f'<button type="submit" class="{BUTTON_VARIANTS["ghost-danger"]}"',
            form.group("body"),
        )


class NoteDeleteTests(DeleteFormTestCase):
    def setUp(self):
        self.note = Note.objects.create(date="2025-11-24", body="# P\nx")
        self.url = reverse("note_taking:delete_note", args=[self.note.pk])

    def test_formulaire_de_suppression_avec_confirmation(self):
        html = self.client.get(
            reverse("note_taking:note_detail", args=[self.note.pk])
        ).content.decode()

        self.assert_delete_form(
            html, self.url, "Supprimer définitivement la note du 24 novembre 2025 ?"
        )

    def test_pas_de_page_de_confirmation(self):
        self.assertEqual(self.client.get(self.url).status_code, 405)
        self.assertTrue(Note.objects.filter(pk=self.note.pk).exists())

    def test_suppression_par_post(self):
        response = self.client.post(self.url)

        self.assertRedirects(response, reverse("note_taking:notes_list"))
        self.assertFalse(Note.objects.filter(pk=self.note.pk).exists())


class TodoDeleteTests(DeleteFormTestCase):
    def setUp(self):
        self.todo = Todo.objects.create(
            project=Project.objects.get_or_create(name="P")[0], title="Relire"
        )
        self.url = reverse("todolist:todo_delete", args=[self.todo.pk])

    def test_formulaire_de_suppression_avec_confirmation(self):
        html = self.client.get(
            reverse("todolist:todo_detail", args=[self.todo.pk])
        ).content.decode()

        self.assert_delete_form(
            html, self.url, "Supprimer définitivement la tâche « Relire » ?"
        )

    def test_pas_de_page_de_confirmation(self):
        self.assertEqual(self.client.get(self.url).status_code, 405)
        self.assertTrue(Todo.objects.filter(pk=self.todo.pk).exists())

    def test_suppression_par_post_avec_message(self):
        response = self.client.post(self.url)

        self.assertRedirects(response, reverse("todolist:todo_list"))
        self.assertFalse(Todo.objects.filter(pk=self.todo.pk).exists())
        self.assertEqual(
            [str(m) for m in get_messages(response.wsgi_request)],
            ["La tâche « Relire » est supprimée."],
        )
