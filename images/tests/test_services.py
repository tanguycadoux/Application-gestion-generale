"""Tests de l'import d'images."""

import shutil
import tempfile
import unittest

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings

from images import exceptions
from images.exceptions import ImageAlreadyExistsError
from images.models import Image
from images.services import import_image
from images.tests.files import image_file, png

# Absente tant que #224 n'est pas corrigée.
InvalidImageError = getattr(exceptions, "InvalidImageError", Exception)

MEDIA_ROOT = tempfile.mkdtemp()

SVG = b'<svg xmlns="http://www.w3.org/2000/svg" width="1" height="1"/>'


@override_settings(MEDIA_ROOT=MEDIA_ROOT)
class ImportImageTests(TestCase):
    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(MEDIA_ROOT, ignore_errors=True)

    def test_image_importee(self):
        image = import_image(image_file("banc.png"))

        self.assertEqual(image.name, "banc.png")
        self.assertFalse(image.source)
        self.assertTrue(image.file.name.startswith("note_images/"))

    def test_nom_d_origine_conserve(self):
        """Le fichier peut être renommé par Django, pas la référence."""
        image = import_image(image_file("Capture d’écran 1.png"))

        self.assertEqual(image.name, "Capture d’écran 1.png")
        self.assertNotIn(" ", image.file.name)

    def test_nom_deja_utilise(self):
        import_image(image_file("banc.png"))

        with self.assertRaisesMessage(ImageAlreadyExistsError, "existe déjà"):
            import_image(image_file("banc.png"))
        self.assertEqual(Image.objects.count(), 1)

    @unittest.expectedFailure
    def test_fichier_qui_n_est_pas_une_image_refuse(self):
        """#224 : le contenu est vérifié, pas seulement l'extension."""
        for name, data in (
            ("faux.png", b"du texte"),
            ("tronquee.png", png()[:30]),
            ("faux.svg", b"pas du XML"),
            ("page.svg", b"<html><body/></html>"),
        ):
            with self.subTest(name=name):
                with self.assertRaisesMessage(InvalidImageError, name):
                    import_image(SimpleUploadedFile(name, data))
                self.assertFalse(Image.objects.filter(name=name).exists())

    def test_svg_importe(self):
        image = import_image(SimpleUploadedFile("schema.svg", SVG))

        self.assertTrue(image.is_vector)
        image.file.open("rb")
        with image.file:
            self.assertEqual(image.file.read(), SVG)


DELETE_MEDIA_ROOT = tempfile.mkdtemp()


@override_settings(MEDIA_ROOT=DELETE_MEDIA_ROOT)
class DeleteImageTests(TestCase):
    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(DELETE_MEDIA_ROOT, ignore_errors=True)

    def use(self, image: Image) -> None:
        from core.models import Project
        from note_taking.models import Note, NotePart, NotePartImageLink

        note = Note.objects.create(date="2025-11-24")
        part = NotePart.objects.create(
            note=note, project=Project.objects.create(name="P")
        )
        NotePartImageLink.objects.create(note_part=part, image=image)

    def test_image_inutilisee_supprimee_avec_son_fichier(self):
        from images.services import delete_image

        image = import_image(image_file("banc.png"))
        storage, name = image.file.storage, image.file.name

        with self.captureOnCommitCallbacks(execute=True):
            delete_image(image)

        self.assertFalse(Image.objects.filter(pk=image.pk).exists())
        self.assertFalse(storage.exists(name))

    def test_image_utilisee_refusee(self):
        from images.exceptions import ImageInUseError
        from images.services import delete_image

        image = import_image(image_file("banc.png"))
        self.use(image)

        with self.assertRaises(ImageInUseError):
            delete_image(image)

        self.assertTrue(Image.objects.filter(pk=image.pk).exists())
        self.assertTrue(image.file.storage.exists(image.file.name))
