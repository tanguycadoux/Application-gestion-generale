"""Tests de la suppression : un seul fonctionnement, confirmation par popover (#126).

Un bouton qui ouvre une popover native (`{% confirm_button %}`, #292) contenant un
formulaire POST, et des vues limitées à POST, sans page de confirmation.
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
    def assert_delete_popover(
        self, html: str, popover_id: str, action: str, message: str
    ):
        """Le bouton ouvre une popover native qui porte le message et le formulaire :
        « Annuler » (sans envoi), puis « Supprimer » en danger (#292)."""
        self.assertRegex(
            html,
            rf'<button type="button" class="{re.escape(BUTTON_VARIANTS["ghost-danger"])}"'
            rf'[^>]*popovertarget="{popover_id}"',
        )
        popover = re.search(
            rf'<div id="{popover_id}" popover class="confirm-popover[^"]*">(.*?)</div>',
            html,
            re.DOTALL,
        )
        assert popover is not None, html
        self.assertIn(message, popover[1])
        form = re.search(r"<form .*?</form>", popover[1], re.DOTALL)
        assert form is not None
        self.assertIn(f'action="{action}"', form[0])
        self.assertIn("csrfmiddlewaretoken", form[0])
        self.assertNotIn("data-confirm", html)
        cancel = form[0].index('popovertargetaction="hide"')
        submit = form[0].index('type="submit"')
        self.assertLess(cancel, submit)
        self.assertIn(BUTTON_VARIANTS["danger"], form[0][submit - 10 :])


class NoteDeleteTests(DeleteFormTestCase):
    def setUp(self):
        self.note = Note.objects.create(date="2025-11-24", body="# P\nx")
        self.url = reverse("note_taking:delete_note", args=[self.note.date])

    def test_formulaire_de_suppression_avec_confirmation(self):
        html = self.client.get(
            reverse("note_taking:note_detail", args=[self.note.date])
        ).content.decode()

        self.assert_delete_popover(
            page_header(html),
            "delete-note",
            self.url,
            "Supprimer définitivement la note du 24 novembre 2025 ?",
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

    def test_confirmation_par_une_popover_native(self):
        """Le bouton de l'en-tête ouvre une popover qui porte le message et le
        formulaire : « Annuler » (sans envoi), puis « Supprimer » en danger."""
        html = self.client.get(
            reverse("todolist:todo_detail", args=[self.todo.pk])
        ).content.decode()

        header = page_header(html)
        self.assertRegex(
            header,
            r'<button type="button"[^>]*aria-label="Supprimer la tâche"'
            r'[^>]*popovertarget="delete-confirm"',
        )
        popover = re.search(
            r'<div id="delete-confirm" popover class="confirm-popover[^"]*">(.*?)</div>',
            header,
            re.DOTALL,
        )
        assert popover is not None, header
        self.assertIn("Supprimer définitivement la tâche « Relire » ?", popover[1])
        form = re.search(r"<form .*?</form>", popover[1], re.DOTALL)
        assert form is not None
        self.assertIn(f'action="{self.url}"', form[0])
        self.assertIn("csrfmiddlewaretoken", form[0])
        self.assertNotIn("data-confirm", form[0])
        cancel = form[0].index('popovertargetaction="hide"')
        submit = form[0].index('type="submit"')
        self.assertLess(cancel, submit)
        self.assertIn(BUTTON_VARIANTS["danger"], form[0][submit - 10 :])

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
