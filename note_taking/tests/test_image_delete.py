"""Tests de la suppression d'une image depuis sa page de détail (#85)."""

import shutil
import tempfile

from django.contrib.messages import get_messages
from django.contrib.staticfiles import finders
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse

from core.models import Project
from images.models import Image
from images.services import import_image
from note_taking.models import Note, NotePart, NotePartImageLink

MEDIA_ROOT = tempfile.mkdtemp()


@override_settings(MEDIA_ROOT=MEDIA_ROOT)
class ImageDeleteTests(TestCase):
    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(MEDIA_ROOT, ignore_errors=True)

    def setUp(self):
        self.image = import_image(SimpleUploadedFile("banc.png", b"image"))

    def use(self, note_date: str = "2025-11-24") -> None:
        note = Note.objects.get_or_create(date=note_date)[0]
        part = NotePart.objects.create(
            note=note, project=Project.objects.get_or_create(name="P")[0]
        )
        NotePartImageLink.objects.create(note_part=part, image=self.image)

    def delete(self):
        with self.captureOnCommitCallbacks(execute=True):
            return self.client.post(
                reverse("note_taking:delete_image", args=[self.image.pk])
            )

    def detail(self) -> str:
        url = reverse("note_taking:image_detail", args=[self.image.pk])
        return self.client.get(url).content.decode()

    def test_suppression_d_une_image_inutilisee(self):
        response = self.delete()

        self.assertRedirects(response, reverse("note_taking:images_list"))
        self.assertFalse(Image.objects.filter(pk=self.image.pk).exists())
        self.assertIn(
            "L'image banc.png a été supprimée.",
            [m.message for m in get_messages(response.wsgi_request)],
        )

    def test_suppression_refusee_si_l_image_est_utilisee(self):
        self.use()

        response = self.delete()

        self.assertRedirects(
            response, reverse("note_taking:image_detail", args=[self.image.pk])
        )
        self.assertTrue(Image.objects.filter(pk=self.image.pk).exists())
        self.assertEqual(
            [m.level_tag for m in get_messages(response.wsgi_request)], ["error"]
        )

    def test_suppression_uniquement_en_post(self):
        response = self.client.get(
            reverse("note_taking:delete_image", args=[self.image.pk])
        )

        self.assertEqual(response.status_code, 405)

    def test_bouton_actif_avec_confirmation_pour_une_image_inutilisee(self):
        html = self.detail()

        self.assertIn(
            f'action="{reverse("note_taking:delete_image", args=[self.image.pk])}"',
            html,
        )
        self.assertIn("data-confirm=", html)
        self.assertNotRegex(html, r"<button[^>]*disabled")

    def test_bouton_desactive_avec_la_raison_si_l_image_est_utilisee(self):
        self.use("2025-11-24")
        self.use("2026-02-03")

        html = self.detail()

        self.assertRegex(html, r"<button[^>]*disabled")
        self.assertIn("utilisée par 2 notes", html)

    def test_script_de_confirmation_charge(self):
        html = self.detail()

        self.assertIsNotNone(finders.find("core/confirm.js"))
        self.assertIn("core/confirm.js", html)

    def test_raison_juste_sous_le_bouton(self):
        self.use()

        html = self.detail()

        self.assertRegex(html, r"</button>\s*<p[^>]*>Suppression impossible")
