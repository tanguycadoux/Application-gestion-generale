"""Tests de l'export des notes en archive zip de fichiers qmd (#64)."""

import io
import shutil
import tempfile
import zipfile

from django.core.files.base import ContentFile
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse

from images.models import Image
from images.services import import_image
from note_taking.models import Note
from note_taking.qmd.files import (
    check_metadata_date,
    read_note_file,
    split_front_matter,
)

MEDIA_ROOT = tempfile.mkdtemp()


class NoteToQmdTests(TestCase):
    def to_qmd(self, body: str, note_date: str = "2025-11-24") -> str:
        from note_taking.qmd.export import note_to_qmd

        return note_to_qmd(Note(date=note_date, body=body))

    def test_bloc_d_en_tete_regenere(self):
        self.assertEqual(
            self.to_qmd("# P\nTexte"), "---\ndate: 2025-11-24\n---\n\n# P\nTexte"
        )

    def test_fins_de_ligne_du_corps_conservees(self):
        self.assertEqual(
            self.to_qmd("# P\r\nTexte"),
            "---\r\ndate: 2025-11-24\r\n---\r\n\r\n# P\r\nTexte",
        )

    def test_chemins_d_images_normalises(self):
        qmd = self.to_qmd(
            "![A](images/a.png){width=80%}\n![B](../autre/dossier/b.png)\n"
            "![C](https://example.com/c.png)"
        )

        self.assertIn("![A](images/a.png){width=80%}", qmd)
        self.assertIn("![B](images/b.png)", qmd)
        self.assertIn("![C](https://example.com/c.png)", qmd)

    def test_relu_a_l_identique_par_l_import(self):
        """Le fichier exporté redonne la même date et le même corps."""
        body = "# P\r\n\r\n::: {.metadata}\r\ntags: [a]\r\n:::\r\nTexte\r\n"
        file = SimpleUploadedFile("2025-11-24.qmd", self.to_qmd(body).encode("utf-8"))

        note_date, content = read_note_file(file)
        metadata, read_body = split_front_matter(content)

        check_metadata_date(note_date, metadata)
        self.assertEqual(read_body, body)


@override_settings(MEDIA_ROOT=MEDIA_ROOT)
class NotesArchiveTests(TestCase):
    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(MEDIA_ROOT, ignore_errors=True)

    def setUp(self):
        Note.objects.create(date="2025-11-24", body="# P\n![A](images/banc.png)")
        Note.objects.create(date="2026-02-03", body="# Q\nTexte")
        import_image(SimpleUploadedFile("banc.png", b"contenu-png"))

    def archive(self) -> zipfile.ZipFile:
        from note_taking.qmd.export import write_notes_archive

        buffer = io.BytesIO()
        write_notes_archive(buffer)
        return zipfile.ZipFile(buffer)

    def test_une_note_par_fichier_et_les_images(self):
        archive = self.archive()

        self.assertEqual(
            sorted(archive.namelist()),
            ["2025-11-24.qmd", "2026-02-03.qmd", "images/banc.png"],
        )
        self.assertEqual(archive.read("images/banc.png"), b"contenu-png")
        self.assertEqual(
            archive.read("2026-02-03.qmd").decode("utf-8"),
            "---\ndate: 2026-02-03\n---\n\n# Q\nTexte",
        )

    def test_image_sous_son_nom_d_origine(self):
        """Le fichier stocké peut avoir été renommé : l'archive garde le nom des notes."""
        image = Image.objects.create(name="Capture d’écran 1.png")
        image.file.save("capture_ecran_1.png", ContentFile(b"x"))

        self.assertIn("images/Capture d’écran 1.png", self.archive().namelist())


@override_settings(MEDIA_ROOT=MEDIA_ROOT)
class ExportViewTests(TestCase):
    def test_telechargement_de_l_archive(self):
        Note.objects.create(date="2025-11-24", body="# P\nx")

        response = self.client.get(reverse("note_taking:export_notes"))

        self.assertEqual(response["Content-Type"], "application/zip")
        self.assertRegex(
            response["Content-Disposition"],
            r'^attachment; filename="notes-\d{4}-\d{2}-\d{2}\.zip"$',
        )
        archive = zipfile.ZipFile(io.BytesIO(b"".join(response.streaming_content)))
        self.assertEqual(archive.namelist(), ["2025-11-24.qmd"])

    def test_bouton_sur_la_liste_des_notes(self):
        response = self.client.get(reverse("note_taking:notes_list"))

        self.assertContains(response, f'href="{reverse("note_taking:export_notes")}"')
        self.assertContains(response, "Exporter toutes les notes")
