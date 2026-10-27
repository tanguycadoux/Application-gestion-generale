"""Tests des vues d'import, de mise à jour et d'édition des notes."""

import re
import shutil
import tempfile

from django.contrib.messages import get_messages
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse

from core.models import Section
from core.tests.debug_urls import DebugUrlsTestCase
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


class UpdateSourceFileViewTests(ViewTestCase):
    def setUp(self):
        self.note = Note.objects.create(date="2025-11-24", body=HEADER + "# P\nx")
        self.url = reverse("note_taking:update_source_file", args=[self.note.date])

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
            reverse("note_taking:update_source_file", args=["2000-01-01"])
        )

        self.assertEqual(response.status_code, 404)

    def test_get_refuse(self):
        """#219 : la mise à jour n'accepte qu'un POST."""
        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 405)

    def test_retour_sur_la_page_de_la_note(self):
        """#219 : la redirection ne dépend pas de l'en-tête Referer."""
        response = self.client.post(
            self.url,
            {"note_update_source_file": qmd_file("2025-11-24.qmd", HEADER + "# P\ny")},
            HTTP_REFERER="https://exemple.org/",
        )

        self.assertRedirects(
            response,
            reverse("note_taking:note_detail", args=[self.note.date]),
            fetch_redirect_response=False,
        )


class NoteListSortTests(ViewTestCase):
    """#219 : seuls les tris proposés par l'interface sont acceptés."""

    def setUp(self):
        for day in ("2025-11-24", "2025-11-26", "2025-11-25"):
            Note.objects.create(date=day, body="# P\nx")
        self.url = reverse("note_taking:notes_list")

    def dates(self, response) -> list[str]:
        return [str(note.date) for note in response.context["notes"]]

    def test_tri_par_date(self):
        response = self.client.get(self.url, {"sort": "date", "direction": "asc"})

        self.assertEqual(
            self.dates(response), ["2025-11-24", "2025-11-25", "2025-11-26"]
        )

    def test_tri_inconnu_revient_au_tri_par_defaut(self):
        for params in (
            {"sort": "foo", "direction": "asc"},
            {"sort": "body", "direction": "asc"},
            {"sort": "date", "direction": "foo"},
        ):
            with self.subTest(params=params):
                response = self.client.get(self.url, params)

                self.assertEqual(response.status_code, 200)
                self.assertEqual(
                    self.dates(response), ["2025-11-26", "2025-11-25", "2025-11-24"]
                )
                self.assertIsNone(response.context["sort"])


class NoteFormViewTests(ViewTestCase):
    def test_creation(self):
        response = self.client.post(
            reverse("note_taking:new_note"), {"date": "2025-11-24", "body": "# P\nx"}
        )

        note = Note.objects.get()
        self.assertRedirects(
            response,
            reverse("note_taking:note_detail", args=[note.date]),
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
            reverse("note_taking:edit_note", args=[note.date]),
            {"date": "2025-11-24", "body": "# P\n### A\ny"},
        )

        note.refresh_from_db()
        self.assertEqual(note.body, "# P\n### A\ny")
        self.assertEqual(list(note.parts.values_list("content", flat=True)), ["y"])

    def test_modification_interrompue_garde_les_parts_d_avant(self):
        """#221 : le texte est enregistré, les note parts d'avant restent intactes."""
        note = Note.objects.create(date="2025-11-24", body="# P\nx")
        process_note_parts(note)
        body = "# P\ny\n# Q\n![a](absente.png)"

        response = self.client.post(
            reverse("note_taking:edit_note", args=[note.date]),
            {"date": "2025-11-24", "body": body},
        )

        note.refresh_from_db()
        self.assertEqual(note.body, body)
        self.assertEqual(list(note.parts.values_list("content", flat=True)), ["x"])
        self.assertEqual(self.levels(response), ["error"])

    def test_modification_contenu_non_traitable(self):
        note = Note.objects.create(date="2025-11-24", body="# P\nx")

        response = self.client.post(
            reverse("note_taking:edit_note", args=[note.date]),
            {"date": "2025-11-24", "body": "# P\n![a](absente.png)"},
        )

        note.refresh_from_db()
        self.assertEqual(note.body, "# P\n![a](absente.png)")
        self.assertEqual(self.levels(response), ["error"])


class NoteJsonViewTests(DebugUrlsTestCase):
    def test_analyse_au_format_json(self):
        note = Note.objects.create(date="2025-11-24", body=HEADER + "# P\n### A\nx")

        response = self.client.get(reverse("note_taking:note_json", args=[note.date]))

        self.assertEqual(
            response.json(),
            {
                "file date": "2025-11-24",
                "note metadata": {"date": "2025-11-24"},
                "content": [
                    {"project": "P", "path": ["A"], "tags": [], "content": ["x"]}
                ],
            },
        )

    def test_note_sans_contenu(self):
        note = Note.objects.create(date="2025-11-24", body="")

        response = self.client.get(reverse("note_taking:note_json", args=[note.date]))

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
            reverse("note_taking:note_detail", args=[note.date]),
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
            reverse("note_taking:note_detail", args=[self.note.date])
        )

        self.assertRenderedAsIs(response)

    def test_resultats_de_recherche(self):
        response = self.client.post(
            reverse("note_taking:notes_search"),
            {"subjects": [str(Section.objects.get(name="S").pk)]},
        )

        self.assertRenderedAsIs(response)


class RenderedContentContainerTests(ViewTestCase):
    """Le contenu rendu est placé dans un conteneur stylé (listes visibles, #80)."""

    RAW = "# P\n## S\nPremier paragraphe.\n\n- un\n- deux"

    # Le paragraphe rendu se trouve dans le conteneur, avant toute fermeture de div.
    CONTAINER_REGEX = re.compile(
        r'<div class="rendered-content">(?:(?!</div>).)*<p>Premier paragraphe\.</p>',
        re.DOTALL,
    )

    def setUp(self):
        self.note = Note.objects.create(date="2025-11-24", body=self.RAW)
        process_note_parts(self.note)

    def test_detail_de_la_note(self):
        response = self.client.get(
            reverse("note_taking:note_detail", args=[self.note.date])
        )

        self.assertRegex(response.content.decode(), self.CONTAINER_REGEX)

    def test_resultats_de_recherche(self):
        response = self.client.post(
            reverse("note_taking:notes_search"),
            {"subjects": [str(Section.objects.get(name="S").pk)]},
        )

        self.assertRegex(response.content.decode(), self.CONTAINER_REGEX)
