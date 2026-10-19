"""Tests de l'import d'images."""

import shutil
import tempfile

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings

from images.exceptions import ImageAlreadyExistsError
from images.models import Image
from images.services import import_image

MEDIA_ROOT = tempfile.mkdtemp()


def image_file(name: str) -> SimpleUploadedFile:
    return SimpleUploadedFile(name, b"image", content_type="image/png")


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
