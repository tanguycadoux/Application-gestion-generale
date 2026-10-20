"""Tests du réimport d'une archive de notes (#114)."""

import io
import shutil
import tempfile
import unittest
import zipfile

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse

from images.models import Image
from images.services import import_image
from note_taking.exceptions import NoteError
from note_taking.models import Note

MEDIA_ROOT = tempfile.mkdtemp()


def qmd(note_date: str, body: str) -> bytes:
    return f"---\ndate: {note_date}\n---\n\n{body}".encode()


def archive(**entries: bytes) -> SimpleUploadedFile:
    """Archive zip ; les clés utilisent __ pour / (images__a.png)."""
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as zip_file:
        for name, data in entries.items():
            zip_file.writestr(name.replace("__", "/"), data)
    return SimpleUploadedFile("notes.zip", buffer.getvalue())


@override_settings(MEDIA_ROOT=MEDIA_ROOT)
class ImportArchiveServiceTests(TestCase):
    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(MEDIA_ROOT, ignore_errors=True)

    def run_import(self, file):
        from note_taking.qmd.archive_import import import_notes_archive

        return import_notes_archive(file)

    @unittest.expectedFailure
    def test_notes_et_images_nouvelles_importees(self):
        report = self.run_import(
            archive(
                **{
                    "2025-11-24.qmd": qmd("2025-11-24", "# P\n![A](images/banc.png)"),
                    "images__banc.png": b"banc",
                }
            )
        )

        self.assertEqual([n.date.isoformat() for n in report.created], ["2025-11-24"])
        self.assertEqual(report.images_imported, ["banc.png"])
        note = Note.objects.get(date="2025-11-24")
        self.assertEqual(note.parts.get().images.get().name, "banc.png")

    @unittest.expectedFailure
    def test_note_existante_ignoree_sans_modification(self):
        existing = Note.objects.create(date="2025-11-24", body="# P\nVersion en base")

        report = self.run_import(
            archive(**{"2025-11-24.qmd": qmd("2025-11-24", "# P\nVersion archive")})
        )

        self.assertEqual(report.skipped, [existing])
        self.assertEqual(report.created, [])
        existing.refresh_from_db()
        self.assertEqual(existing.body, "# P\nVersion en base")

    @unittest.expectedFailure
    def test_image_existante_gardee(self):
        image = import_image(SimpleUploadedFile("banc.png", b"en base"))

        report = self.run_import(archive(**{"images__banc.png": b"archive"}))

        self.assertEqual(report.images_kept, ["banc.png"])
        with image.file.open("rb") as file:
            self.assertEqual(file.read(), b"en base")
        self.assertEqual(Image.objects.count(), 1)

    @unittest.expectedFailure
    def test_une_note_en_erreur_n_empeche_pas_les_autres(self):
        report = self.run_import(
            archive(
                **{
                    "2025-11-24.qmd": qmd(
                        "2025-11-24", "# P\n![A](images/absente.png)"
                    ),
                    "2025-11-25.qmd": qmd("2025-11-25", "# P\nx"),
                }
            )
        )

        self.assertEqual([n.date.isoformat() for n in report.created], ["2025-11-25"])
        self.assertEqual([name for name, _ in report.failed], ["2025-11-24.qmd"])
        self.assertFalse(Note.objects.filter(date="2025-11-24").exists())

    @unittest.expectedFailure
    def test_entrees_non_reconnues_ignorees(self):
        report = self.run_import(
            archive(
                **{
                    "notes__2025-11-24.qmd": qmd("2025-11-24", "# P\nx"),
                    "images__sous__c.png": b"c",
                    "LISEZMOI.txt": b"x",
                }
            )
        )

        self.assertEqual(
            sorted(report.ignored),
            ["LISEZMOI.txt", "images/sous/c.png", "notes/2025-11-24.qmd"],
        )
        self.assertFalse(Note.objects.exists())
        self.assertFalse(Image.objects.exists())

    @unittest.expectedFailure
    def test_fichier_qui_n_est_pas_une_archive(self):
        with self.assertRaises(NoteError):
            self.run_import(SimpleUploadedFile("notes.zip", b"pas un zip"))

    @unittest.expectedFailure
    def test_export_puis_reimport_dans_une_base_vide(self):
        from note_taking.qmd.export import write_notes_archive

        import_image(SimpleUploadedFile("banc.png", b"banc"))
        Note.objects.create(date="2025-11-24", body="# P\r\n![A](images/banc.png)\r\n")
        buffer = io.BytesIO()
        write_notes_archive(buffer)
        Note.objects.all().delete()
        Image.objects.all().delete()

        report = self.run_import(SimpleUploadedFile("notes.zip", buffer.getvalue()))

        self.assertEqual(len(report.created), 1)
        self.assertEqual(Note.objects.get().body, "# P\r\n![A](images/banc.png)\r\n")
        self.assertEqual(Image.objects.get().name, "banc.png")


@override_settings(MEDIA_ROOT=MEDIA_ROOT)
class ImportArchiveViewTests(TestCase):
    def post(self, file=None):
        data = {"archive_import": file} if file else {}
        return self.client.post(reverse("note_taking:import_archive"), data)

    @unittest.expectedFailure
    def test_compte_rendu_affiche(self):
        existing = Note.objects.create(date="2025-11-24", body="# P\nx")

        response = self.post(
            archive(
                **{
                    "2025-11-24.qmd": qmd("2025-11-24", "# P\ny"),
                    "2025-11-25.qmd": qmd("2025-11-25", "# P\nz"),
                }
            )
        )

        self.assertContains(response, "Notes créées (1)")
        self.assertContains(response, "Notes ignorées, déjà en base (1)")
        self.assertContains(
            response, f'href="{reverse("note_taking:note_detail", args=[existing.pk])}"'
        )

    @unittest.expectedFailure
    def test_archive_invalide(self):
        response = self.post(SimpleUploadedFile("notes.zip", b"pas un zip"))

        self.assertRedirects(response, reverse("note_taking:notes_list"))

    @unittest.expectedFailure
    def test_sans_fichier(self):
        response = self.post()

        self.assertRedirects(response, reverse("note_taking:notes_list"))

    @unittest.expectedFailure
    def test_post_seulement(self):
        response = self.client.get(reverse("note_taking:import_archive"))

        self.assertEqual(response.status_code, 405)

    @unittest.expectedFailure
    def test_formulaire_sur_la_liste_des_notes(self):
        response = self.client.get(reverse("note_taking:notes_list"))

        self.assertContains(
            response, f'action="{reverse("note_taking:import_archive")}"'
        )
        self.assertContains(response, 'name="archive_import"')
