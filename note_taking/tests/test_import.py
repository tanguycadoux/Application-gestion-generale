"""Tests de l'import unifié : notes qmd, images et archives de l'export (#114)."""

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
from images.tests.files import image_file, png
from note_taking.models import Note

MEDIA_ROOT = tempfile.mkdtemp()


def qmd(note_date: str, body: str) -> bytes:
    return f"---\ndate: {note_date}\n---\n\n{body}".encode()


def qmd_file(note_date: str, body: str, name: str = "") -> SimpleUploadedFile:
    return SimpleUploadedFile(name or f"{note_date}.qmd", qmd(note_date, body))


def archive(name: str = "notes.zip", **entries: bytes) -> SimpleUploadedFile:
    """Archive zip ; les clés utilisent __ pour / (images__a.png)."""
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as zip_file:
        for entry, data in entries.items():
            zip_file.writestr(entry.replace("__", "/"), data)
    return SimpleUploadedFile(name, buffer.getvalue())


@override_settings(MEDIA_ROOT=MEDIA_ROOT)
class ImportTestCase(TestCase):
    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(MEDIA_ROOT, ignore_errors=True)

    def run_import(self, *files):
        from note_taking.importing import import_files

        return import_files(list(files))


class ImportArchiveTests(ImportTestCase):
    """Un zip est l'archive de l'export : qmd à la racine, images/<nom>."""

    def test_notes_et_images_nouvelles_importees(self):
        report = self.run_import(
            archive(
                **{
                    "2025-11-24.qmd": qmd("2025-11-24", "# P\n![A](images/banc.png)"),
                    "images__banc.png": png("banc"),
                }
            )
        )

        self.assertEqual([n.date.isoformat() for n in report.created], ["2025-11-24"])
        self.assertEqual(report.images_imported, ["banc.png"])
        note = Note.objects.get(date="2025-11-24")
        self.assertEqual(note.parts.get().images.get().name, "banc.png")

    def test_note_existante_ignoree_sans_modification(self):
        existing = Note.objects.create(date="2025-11-24", body="# P\nVersion en base")

        report = self.run_import(
            archive(**{"2025-11-24.qmd": qmd("2025-11-24", "# P\nVersion archive")})
        )

        self.assertEqual(report.skipped, [existing])
        self.assertEqual(report.created, [])
        existing.refresh_from_db()
        self.assertEqual(existing.body, "# P\nVersion en base")

    def test_image_existante_gardee(self):
        image = import_image(image_file("banc.png", "en base"))

        report = self.run_import(archive(**{"images__banc.png": png("archive")}))

        self.assertEqual(report.images_kept, ["banc.png"])
        with image.file.open("rb") as file:
            self.assertEqual(file.read(), png("en base"))
        self.assertEqual(Image.objects.count(), 1)

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

    def test_entrees_non_reconnues_ignorees(self):
        report = self.run_import(
            archive(
                **{
                    "notes__2025-11-24.qmd": qmd("2025-11-24", "# P\nx"),
                    "images__sous__c.png": png("c"),
                    "LISEZMOI.txt": b"x",
                }
            )
        )

        self.assertEqual(
            sorted(report.ignored),
            [
                "notes.zip/LISEZMOI.txt",
                "notes.zip/images/sous/c.png",
                "notes.zip/notes/2025-11-24.qmd",
            ],
        )
        self.assertFalse(Note.objects.exists())
        self.assertFalse(Image.objects.exists())

    def test_zip_invalide_signale_sans_bloquer_les_autres_fichiers(self):
        report = self.run_import(
            SimpleUploadedFile("notes.zip", b"pas un zip"),
            qmd_file("2025-11-24", "# P\nx"),
        )

        self.assertEqual([name for name, _ in report.failed], ["notes.zip"])
        self.assertEqual(len(report.created), 1)

    def test_export_puis_reimport_dans_une_base_vide(self):
        from note_taking.qmd.export import write_notes_archive

        import_image(image_file("banc.png", "banc"))
        Note.objects.create(date="2025-11-24", body="# P\r\n![A](images/banc.png)\r\n")
        buffer = io.BytesIO()
        write_notes_archive(buffer)
        Note.objects.all().delete()
        Image.objects.all().delete()

        report = self.run_import(SimpleUploadedFile("notes.zip", buffer.getvalue()))

        self.assertEqual(len(report.created), 1)
        self.assertEqual(Note.objects.get().body, "# P\r\n![A](images/banc.png)\r\n")
        self.assertEqual(Image.objects.get().name, "banc.png")


class ImportFilesTests(ImportTestCase):
    """Des fichiers sélectionnés directement : notes qmd et images."""

    def test_note_seule(self):
        report = self.run_import(qmd_file("2025-11-24", "# P\nx"))

        self.assertEqual([n.date.isoformat() for n in report.created], ["2025-11-24"])

    def test_image_seule(self):
        report = self.run_import(image_file("banc.png"))

        self.assertEqual(report.images_imported, ["banc.png"])
        self.assertTrue(Image.objects.filter(name="banc.png").exists())

    def test_note_et_ses_images_selectionnees_ensemble(self):
        """Les images sont importées avant les notes, quel que soit l'ordre choisi."""
        report = self.run_import(
            qmd_file("2025-11-24", "# P\n![A](images/banc.png)"), image_file("banc.png")
        )

        self.assertEqual(report.failed, [])
        note = Note.objects.get(date="2025-11-24")
        self.assertEqual(note.parts.get().images.get().name, "banc.png")

    @unittest.expectedFailure
    def test_image_invalide_signalee_sans_bloquer_les_autres(self):
        """#224 : un fichier image illisible est en erreur, les autres sont importés."""
        report = self.run_import(
            SimpleUploadedFile("faux.png", b"du texte"), image_file("banc.png")
        )

        self.assertEqual([name for name, _ in report.images_failed], ["faux.png"])
        self.assertEqual(report.images_imported, ["banc.png"])
        self.assertFalse(Image.objects.filter(name="faux.png").exists())

    def test_image_deja_en_base_gardee_sans_doublon(self):
        import_image(image_file("banc.png", "en base"))

        report = self.run_import(image_file("banc.png", "nouvelle"))

        self.assertEqual(report.images_kept, ["banc.png"])
        self.assertEqual(report.failed, [])
        self.assertEqual(Image.objects.count(), 1)

    def test_note_deja_en_base_ignoree(self):
        existing = Note.objects.create(date="2025-11-24", body="# P\nen base")

        report = self.run_import(qmd_file("2025-11-24", "# P\nnouvelle"))

        self.assertEqual(report.skipped, [existing])
        existing.refresh_from_db()
        self.assertEqual(existing.body, "# P\nen base")

    def test_nom_de_note_invalide_en_erreur(self):
        report = self.run_import(
            qmd_file("2025-11-24", "# P\nx", name="note.qmd"),
            qmd_file("2025-11-25", "y"),
        )

        self.assertEqual([name for name, _ in report.failed], ["note.qmd"])
        self.assertEqual(len(report.created), 1)

    def test_fichier_d_un_autre_type_ignore(self):
        report = self.run_import(SimpleUploadedFile("LISEZMOI.txt", b"x"))

        self.assertEqual(report.ignored, ["LISEZMOI.txt"])

    def test_archive_fichiers_et_images_melanges(self):
        report = self.run_import(
            archive(**{"2025-11-24.qmd": qmd("2025-11-24", "# P\nx")}),
            qmd_file("2025-11-25", "# P\ny"),
            image_file("banc.png"),
        )

        self.assertEqual(
            [n.date.isoformat() for n in report.created], ["2025-11-24", "2025-11-25"]
        )
        self.assertEqual(report.images_imported, ["banc.png"])


@override_settings(MEDIA_ROOT=MEDIA_ROOT)
class ImportViewTests(TestCase):
    def post(self, *files):
        data = {"import_files": list(files)} if files else {}
        return self.client.post(reverse("note_taking:import_files"), data)

    def test_compte_rendu_affiche(self):
        existing = Note.objects.create(date="2025-11-24", body="# P\nx")

        response = self.post(
            qmd_file("2025-11-24", "# P\ny"), qmd_file("2025-11-25", "z")
        )

        self.assertContains(response, "Notes créées (1)")
        self.assertContains(response, "Notes ignorées, déjà en base (1)")
        self.assertContains(
            response, f'href="{reverse("note_taking:note_detail", args=[existing.pk])}"'
        )

    def test_compte_rendu_aussi_pour_un_seul_fichier(self):
        response = self.post(image_file("banc.png"))

        self.assertContains(response, "Images importées (1)")

    def test_sans_fichier(self):
        response = self.post()

        self.assertRedirects(response, reverse("note_taking:notes_list"))

    def test_post_seulement(self):
        response = self.client.get(reverse("note_taking:import_files"))

        self.assertEqual(response.status_code, 405)

    def test_un_seul_formulaire_d_import_sur_la_liste_des_notes(self):
        html = self.client.get(reverse("note_taking:notes_list")).content.decode()

        self.assertIn(f'action="{reverse("note_taking:import_files")}"', html)
        self.assertRegex(html, r'<input type="file" name="import_files"[^>]* multiple')

    def test_boutons_importer_et_exporter_cote_a_cote(self):
        html = self.client.get(reverse("note_taking:notes_list")).content.decode()

        self.assertRegex(
            html,
            r'<span class="material-symbols-rounded">upload</span>Importer</button>'
            r"\s*</form>\s*<a [^>]*" + f'href="{reverse("note_taking:export_notes")}"',
        )
