"""Tests des propriétés du modèle Image."""

from django.test import SimpleTestCase

from images.models import Image


class ImagePropertiesTests(SimpleTestCase):
    def test_format_deduit_de_l_extension(self):
        """Le format (vectoriel ou matriciel) se déduit du fichier."""
        cases = {
            "note_images/schema.svg": True,
            "note_images/SCHEMA.SVG": True,
            "note_images/photo.png": False,
            "note_images/photo.jpg": False,
        }
        for path, expected in cases.items():
            with self.subTest(path=path):
                self.assertIs(Image(name="x", file=path).is_vector, expected)

    def test_modifiable_si_source(self):
        """L'origine se déduit de la source : créée dans l'app si elle existe."""
        self.assertFalse(Image(name="x", file="note_images/a.png").is_editable)
        self.assertTrue(
            Image(
                name="x", file="note_images/a.svg", source="image_sources/a.json"
            ).is_editable
        )
