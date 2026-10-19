"""Tests du corps des notes, stocké sans bloc d'en-tête qmd (#24)."""

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import SimpleTestCase, TestCase
from django.urls import reverse

from note_taking.exceptions import NoteParseError
from note_taking.models import Note
from note_taking.qmd.files import split_front_matter
from note_taking.services import insert_note_in_table, update_note_from_source_file

HEADER = "---\ndate: 2025-11-24\n---\n"


def qmd_file(name: str, content: str) -> SimpleUploadedFile:
    return SimpleUploadedFile(name, content.encode("utf-8"))


class SplitFrontMatterTests(SimpleTestCase):
    def test_sans_en_tete(self):
        self.assertEqual(split_front_matter("# P\nx"), ({}, "# P\nx"))

    def test_en_tete_et_lignes_vides_retires(self):
        self.assertEqual(
            split_front_matter("\n---\ndate: 2025-11-24\nheure: 10:30\n---\n\n# P\nx"),
            ({"date": "2025-11-24", "heure": "10:30"}, "# P\nx"),
        )

    def test_ligne_horizontale_conservee(self):
        self.assertEqual(
            split_front_matter(HEADER + "# P\na\n---\nb"),
            ({"date": "2025-11-24"}, "# P\na\n---\nb"),
        )

    def test_en_tete_non_ferme(self):
        with self.assertRaisesMessage(NoteParseError, "pas fermé"):
            split_front_matter("---\ndate: 2025-11-24\n# P")


class BodyFromFileTests(TestCase):
    def test_import_retire_l_en_tete(self):
        note = insert_note_in_table(qmd_file("2025-11-24.qmd", HEADER + "\n# P\nx"))

        note.refresh_from_db()
        self.assertEqual(note.body, "# P\nx")
        self.assertEqual(note.parts.get().content, "x")

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

    def test_corps_sans_en_tete(self):
        self.post("# P\nx")

        self.assertEqual(Note.objects.get().body, "# P\nx")

    def test_en_tete_coherent_retire(self):
        self.post(HEADER + "# P\nx")

        self.assertEqual(Note.objects.get().body, "# P\nx")

    def test_en_tete_d_une_autre_date_refuse(self):
        response = self.post("---\ndate: 2025-11-25\n---\n# P\nx")

        self.assertFalse(Note.objects.exists())
        self.assertFormError(
            response.context["form"],
            "body",
            "La date du bloc d'en-tête (2025-11-25) ne correspond pas "
            "à la date de la note.",
        )
