"""Tests du formulaire d'une note : chaque champ a un label relié (#122)."""

import re
import unittest

from django.test import TestCase
from django.urls import reverse

from note_taking.models import Note

LABEL_FOR_REGEX = re.compile(r'<label[^>]*\bfor="(?P<for>[^"]+)"')


class NoteFormLabelsTests(TestCase):
    def assert_labelled(self, html: str, tag: str, name: str):
        field = re.search(rf'<{tag}[^>]*\bname="{name}"[^>]*>', html)
        assert field is not None
        field_id = re.search(r'\bid="(?P<id>[^"]+)"', field.group())

        self.assertIsNotNone(field_id, f"le champ {name} n'a pas d'id")
        assert field_id is not None
        self.assertIn(field_id.group("id"), LABEL_FOR_REGEX.findall(html))

    def pages(self):
        note = Note.objects.create(date="2025-11-24", body="# P\nx")
        return {
            "nouvelle note": self.client.get(reverse("note_taking:new_note")),
            "édition": self.client.get(
                reverse("note_taking:edit_note", args=[note.pk])
            ),
        }

    @unittest.expectedFailure
    def test_champ_date_relie_a_son_label(self):
        for page, response in self.pages().items():
            with self.subTest(page=page):
                self.assert_labelled(response.content.decode(), "input", "date")

    @unittest.expectedFailure
    def test_corps_relie_a_un_label(self):
        for page, response in self.pages().items():
            with self.subTest(page=page):
                self.assert_labelled(response.content.decode(), "textarea", "body")
