"""Tests des liens entre note parts et images (#26)."""

import shutil
import tempfile

from django.core.files.uploadedfile import SimpleUploadedFile
from django.db.models import ProtectedError
from django.test import TestCase, override_settings

from images.services import import_image
from note_taking.models import Note
from note_taking.services import process_note_parts

MEDIA_ROOT = tempfile.mkdtemp()


def image_file(name: str) -> SimpleUploadedFile:
    return SimpleUploadedFile(name, b"image", content_type="image/png")


@override_settings(MEDIA_ROOT=MEDIA_ROOT)
class NotePartImagesTests(TestCase):
    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(MEDIA_ROOT, ignore_errors=True)

    def setUp(self):
        self.banc = import_image(image_file("banc.png"))
        self.capteur = import_image(image_file("capteur.png"))

    def process(self, body: str) -> Note:
        note = Note.objects.create(date="2025-11-24", body=body)
        process_note_parts(note)
        return note

    def test_images_liees_a_leur_note_part(self):
        note = self.process(
            "# P\n### A\n![](images/banc.png)\n### B\n![](capteur.png)\n![](banc.png)"
        )

        self.assertEqual(
            {part.tags.get().name: set(part.images.all()) for part in note.parts.all()},
            {"A": {self.banc}, "B": {self.capteur, self.banc}},
        )

    def test_images_d_une_note(self):
        note = self.process("# P\n### A\n![](banc.png)\n### B\n![](banc.png)")

        self.assertEqual(list(note.images), [self.banc])

    def test_liens_recalcules(self):
        note = self.process("# P\n![](banc.png)")

        note.body = "# P\n![](capteur.png)"
        process_note_parts(note)

        self.assertEqual(list(note.images), [self.capteur])
        self.assertFalse(self.banc.note_parts.exists())

    def test_image_utilisee_non_supprimable(self):
        self.process("# P\n![](banc.png)")

        with self.assertRaises(ProtectedError):
            self.banc.delete()

    def test_image_inutilisee_supprimable(self):
        self.capteur.delete()
