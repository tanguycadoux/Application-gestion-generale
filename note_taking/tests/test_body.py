"""Tests du corps des notes, stocké sans bloc d'en-tête qmd (#24)."""

import unittest

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse

from note_taking.models import Note
from note_taking.services import insert_note_in_table, update_note_from_source_file

HEADER = "---\ndate: 2025-11-24\n---\n"


def qmd_file(name: str, content: str) -> SimpleUploadedFile:
    return SimpleUploadedFile(name, content.encode("utf-8"))


class BodyFromFileTests(TestCase):
    @unittest.expectedFailure
    def test_import_retire_l_en_tete(self):
        note = insert_note_in_table(qmd_file("2025-11-24.qmd", HEADER + "\n# P\nx"))

        note.refresh_from_db()
        self.assertEqual(note.body, "# P\nx")
        self.assertEqual(note.parts.get().content, "x")

    @unittest.expectedFailure
    def test_mise_a_jour_retire_l_en_tete(self):
        note = Note.objects.create(date="2025-11-24")

        update_note_from_source_file(
            note, qmd_file("2025-11-24.qmd", HEADER + "# Q\ny")
        )

        note.refresh_from_db()
        self.assertEqual(note.body, "# Q\ny")


class BodyFromFormTests(TestCase):
    def post(self, body: str):
        return self.client.post(
            reverse("note_taking:new_note"), {"date": "2025-11-24", "body": body}
        )

    @unittest.expectedFailure
    def test_corps_sans_en_tete(self):
        self.post("# P\nx")

        self.assertEqual(Note.objects.get().body, "# P\nx")

    @unittest.expectedFailure
    def test_en_tete_coherent_retire(self):
        self.post(HEADER + "# P\nx")

        self.assertEqual(Note.objects.get().body, "# P\nx")

    @unittest.expectedFailure
    def test_en_tete_d_une_autre_date_refuse(self):
        response = self.post("---\ndate: 2025-11-25\n---\n# P\nx")

        self.assertFalse(Note.objects.exists())
        self.assertFormError(
            response.context["form"],
            "body",
            "La date du bloc d'en-tête (2025-11-25) ne correspond pas "
            "à la date de la note.",
        )
