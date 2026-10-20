"""Tests du tableau de la liste des notes : en-têtes de colonne valides (#123)."""

import re
import unittest

from django.test import TestCase
from django.urls import reverse

from note_taking.models import Note

COLUMN_HEAD_REGEX = re.compile(
    r'<(?P<tag>a|button) class="table-column-head .*?</(?P=tag)>', re.DOTALL
)


class NoteListColumnHeadsTests(TestCase):
    def setUp(self):
        Note.objects.create(date="2025-11-24", body="# P\nx")
        html = self.client.get(reverse("note_taking:notes_list")).content.decode()
        self.heads = COLUMN_HEAD_REGEX.findall(html)
        self.heads_html = [m.group() for m in COLUMN_HEAD_REGEX.finditer(html)]

    def test_en_tetes_date_et_projets(self):
        self.assertEqual(self.heads, ["a", "button"])

    @unittest.expectedFailure
    def test_pas_de_paragraphe_dans_les_en_tetes(self):
        for head in self.heads_html:
            with self.subTest(head=head[:40]):
                self.assertNotRegex(head, r"<p[\s>]")

    @unittest.expectedFailure
    def test_libelles_dans_des_span(self):
        for label in ("Date", "Projets"):
            with self.subTest(label=label):
                self.assertTrue(
                    any(
                        re.search(rf"<span>\s*{label}\b", head)
                        for head in self.heads_html
                    )
                )
