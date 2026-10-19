"""Tests des vues d'import, de mise à jour et d'édition des notes."""

import shutil
import tempfile

from django.contrib.messages import get_messages
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse

from images.models import Image
from images.services import import_image
from note_taking.models import Note
from note_taking.services import process_note_parts

MEDIA_ROOT = tempfile.mkdtemp()

HEADER = "---\ndate: 2025-11-24\n---\n"


def qmd_file(name: str, content: str) -> SimpleUploadedFile:
    return SimpleUploadedFile(name, content.encode("utf-8"))


def image_file(name: str) -> SimpleUploadedFile:
    return SimpleUploadedFile(name, b"image", content_type="image/png")


@override_settings(MEDIA_ROOT=MEDIA_ROOT)
class ViewTestCase(TestCase):
    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(MEDIA_ROOT, ignore_errors=True)

    def messages(self, response) -> list[tuple[str, str]]:
        return [(m.level_tag, str(m)) for m in get_messages(response.wsgi_request)]

    def levels(self, response) -> list[str]:
        return [level for level, _ in self.messages(response)]


class ImportNoteViewTests(ViewTestCase):
    url = reverse("note_taking:import_note")

    def post(self, *files):
        return self.client.post(
            self.url, {"note_import": list(files)}, HTTP_REFERER="/note_taking/notes/"
        )

    def test_import_reussi(self):
        response = self.post(qmd_file("2025-11-24.qmd", HEADER + "# P\nx"))

        self.assertRedirects(
            response, "/note_taking/notes/", fetch_redirect_response=False
        )
        self.assertTrue(Note.objects.filter(date="2025-11-24").exists())
        self.assertEqual(self.levels(response), ["success"])

    def test_import_en_erreur(self):
        response = self.post(qmd_file("note.qmd", HEADER + "# P\nx"))

        self.assertFalse(Note.objects.exists())
        self.assertEqual(self.levels(response), ["error"])

    def test_un_echec_n_empeche_pas_les_fichiers_suivants(self):
        response = self.post(
            qmd_file("2025-11-24.qmd", HEADER + "# P\nx"),
            qmd_file("note.qmd", HEADER + "# P\nx"),
            qmd_file("2025-11-25.qmd", "---\ndate: 2025-11-25\n---\n# P\nx"),
        )

        self.assertEqual(Note.objects.count(), 2)
        self.assertEqual(sorted(self.levels(response)), ["error", "success"])
        errors = [text for level, text in self.messages(response) if level == "error"]
        self.assertIn("note.qmd", errors[0])

    def test_aucun_fichier(self):
        response = self.post()

        self.assertEqual(self.levels(response), ["warning"])


class UpdateSourceFileViewTests(ViewTestCase):
    def setUp(self):
        self.note = Note.objects.create(date="2025-11-24", body=HEADER + "# P\nx")
        self.url = reverse("note_taking:update_source_file", args=[self.note.pk])

    def test_mise_a_jour_reussie(self):
        response = self.client.post(
            self.url,
            {"note_update_source_file": qmd_file("2025-11-24.qmd", HEADER + "# P\ny")},
        )

        self.note.refresh_from_db()
        self.assertEqual(self.note.body, "# P\ny")
        self.assertEqual(self.levels(response), ["success"])

    def test_sans_fichier(self):
        response = self.client.post(self.url)

        self.assertEqual(self.levels(response), ["error"])

    def test_fichier_en_erreur(self):
        response = self.client.post(
            self.url,
            {"note_update_source_file": qmd_file("2025-11-25.qmd", HEADER)},
        )

        self.note.refresh_from_db()
        self.assertEqual(self.note.body, HEADER + "# P\nx")
        self.assertEqual(self.levels(response), ["error"])

    def test_note_inexistante(self):
        response = self.client.post(
            reverse("note_taking:update_source_file", args=[999])
        )

        self.assertEqual(response.status_code, 404)


class ImportImagesViewTests(ViewTestCase):
    url = reverse("note_taking:import_images")

    def test_import_reussi(self):
        response = self.client.post(self.url, {"image_import": [image_file("a.png")]})

        self.assertTrue(Image.objects.filter(name="a.png").exists())
        self.assertEqual(self.levels(response), ["success"])

    def test_image_deja_importee(self):
        import_image(image_file("a.png"))

        response = self.client.post(self.url, {"image_import": [image_file("a.png")]})

        self.assertEqual(Image.objects.count(), 1)
        self.assertEqual(self.levels(response), ["error"])


class NoteFormViewTests(ViewTestCase):
    def test_creation(self):
        response = self.client.post(
            reverse("note_taking:new_note"), {"date": "2025-11-24", "body": "# P\nx"}
        )

        note = Note.objects.get()
        self.assertRedirects(
            response,
            reverse("note_taking:note_detail", args=[note.pk]),
            fetch_redirect_response=False,
        )
        self.assertEqual(note.parts.count(), 1)

    def test_creation_contenu_non_traitable(self):
        """La note est enregistrée même si son contenu ne peut pas être traité."""
        response = self.client.post(
            reverse("note_taking:new_note"),
            {"date": "2025-11-24", "body": "# P\n![a](absente.png)"},
        )

        self.assertTrue(Note.objects.exists())
        self.assertEqual(self.levels(response), ["error"])

    def test_modification(self):
        note = Note.objects.create(date="2025-11-24", body="# P\nx")

        self.client.post(
            reverse("note_taking:edit_note", args=[note.pk]),
            {"date": "2025-11-24", "body": "# P\n### A\ny"},
        )

        note.refresh_from_db()
        self.assertEqual(note.body, "# P\n### A\ny")
        self.assertEqual(list(note.parts.values_list("content", flat=True)), ["y"])

    def test_modification_contenu_non_traitable(self):
        note = Note.objects.create(date="2025-11-24", body="# P\nx")

        response = self.client.post(
            reverse("note_taking:edit_note", args=[note.pk]),
            {"date": "2025-11-24", "body": "# P\n![a](absente.png)"},
        )

        note.refresh_from_db()
        self.assertEqual(note.body, "# P\n![a](absente.png)")
        self.assertEqual(self.levels(response), ["error"])


class NoteJsonViewTests(ViewTestCase):
    def test_analyse_au_format_json(self):
        note = Note.objects.create(date="2025-11-24", body=HEADER + "# P\n### A\nx")

        response = self.client.get(reverse("note_taking:note_json", args=[note.pk]))

        self.assertEqual(
            response.json(),
            {
                "file date": "2025-11-24",
                "note metadata": {"date": "2025-11-24"},
                "content": [
                    {"project": "P", "subject": None, "tags": ["A"], "content": ["x"]}
                ],
            },
        )

    def test_note_sans_contenu(self):
        note = Note.objects.create(date="2025-11-24", body="")

        response = self.client.get(reverse("note_taking:note_json", args=[note.pk]))

        self.assertEqual(response.json()["content"], [])


class ClearNotesRemovedTests(ViewTestCase):
    def test_get_ne_supprime_pas_les_notes(self):
        Note.objects.create(date="2025-11-24", body="# P\nx")

        response = self.client.get("/note_taking/notes/clear/")

        self.assertEqual(response.status_code, 404)
        self.assertEqual(Note.objects.count(), 1)

    def test_pages_de_notes_affichees(self):
        note = Note.objects.create(date="2025-11-24", body="# P\nx")

        for url in (
            reverse("note_taking:index"),
            reverse("note_taking:notes_list"),
            reverse("note_taking:note_detail", args=[note.pk]),
        ):
            with self.subTest(url=url):
                self.assertEqual(self.client.get(url).status_code, 200)


class RenderedPartsDisplayTests(ViewTestCase):
    """Le HTML rendu des note parts est affiché tel quel (#56)."""

    RAW = "# P\n## S\nPremier paragraphe.\n\nSecond paragraphe."

    def setUp(self):
        self.note = Note.objects.create(date="2025-11-24", body=self.RAW)
        process_note_parts(self.note)

    def assertRenderedAsIs(self, response):
        html = response.content.decode()
        self.assertIn("<p>Premier paragraphe.</p>", html)
        self.assertNotIn("<p><p>", html)
        self.assertNotIn("</p><br>", html)

    def test_detail_de_la_note(self):
        response = self.client.get(
            reverse("note_taking:note_detail", args=[self.note.pk])
        )

        self.assertRenderedAsIs(response)

    def test_resultats_de_recherche(self):
        response = self.client.post(
            reverse("note_taking:notes_search"), {"subjects": ["S"]}
        )

        self.assertRenderedAsIs(response)
