"""Coller ou déposer une capture d'écran : nom généré, import, réponse JSON (#196)."""

import shutil
import tempfile
from datetime import datetime

from django.contrib.messages import get_messages
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import SimpleTestCase, TestCase, override_settings
from django.urls import reverse

from images.exceptions import InvalidImageError
from images.models import Image
from images.tests.files import png
from note_taking.captures import capture_name, import_capture

MEDIA_ROOT = tempfile.mkdtemp()
NOW = datetime(2025, 11, 24, 14, 30, 12)

SVG = b'<svg xmlns="http://www.w3.org/2000/svg" width="1" height="1"/>'


def upload(
    content: bytes = b"", content_type: str = "image/png", name: str = "image.png"
):
    return SimpleUploadedFile(name, content or png(), content_type=content_type)


class CaptureNameTests(SimpleTestCase):
    def test_horodatage_a_la_seconde(self):
        self.assertEqual(
            capture_name(".png", NOW, taken=set()), "capture-2025-11-24-143012.png"
        )

    def test_suffixe_si_le_nom_est_pris(self):
        taken = {"capture-2025-11-24-143012.png"}

        self.assertEqual(
            capture_name(".png", NOW, taken), "capture-2025-11-24-143012-2.png"
        )

    def test_suffixe_suivant_si_les_deux_sont_pris(self):
        taken = {
            "capture-2025-11-24-143012.png",
            "capture-2025-11-24-143012-2.png",
        }

        self.assertEqual(
            capture_name(".png", NOW, taken), "capture-2025-11-24-143012-3.png"
        )

    def test_meme_seconde_autre_format_pas_de_suffixe(self):
        taken = {"capture-2025-11-24-143012.png"}

        self.assertEqual(
            capture_name(".jpg", NOW, taken), "capture-2025-11-24-143012.jpg"
        )


@override_settings(MEDIA_ROOT=MEDIA_ROOT)
class ImportCaptureTests(TestCase):
    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(MEDIA_ROOT, ignore_errors=True)

    def test_image_importee_sous_un_nom_genere(self):
        image = import_capture(upload(), now=NOW)

        self.assertEqual(image.name, "capture-2025-11-24-143012.png")
        self.assertTrue(Image.objects.filter(name=image.name).exists())

    def test_deux_captures_dans_la_meme_seconde(self):
        first = import_capture(upload(), now=NOW)
        second = import_capture(upload(png("autre")), now=NOW)

        self.assertEqual(first.name, "capture-2025-11-24-143012.png")
        self.assertEqual(second.name, "capture-2025-11-24-143012-2.png")

    def test_extension_selon_le_type(self):
        image = import_capture(upload(SVG, "image/svg+xml", "x.svg"), now=NOW)

        self.assertEqual(image.name, "capture-2025-11-24-143012.svg")

    def test_type_inconnu_refuse(self):
        with self.assertRaises(InvalidImageError):
            import_capture(upload(b"texte", "text/plain", "x.txt"), now=NOW)

        self.assertEqual(Image.objects.count(), 0)

    def test_contenu_qui_n_est_pas_une_image_refuse(self):
        with self.assertRaises(InvalidImageError):
            import_capture(upload(b"pas une image"), now=NOW)

        self.assertEqual(Image.objects.count(), 0)


@override_settings(MEDIA_ROOT=MEDIA_ROOT)
class CaptureViewTests(TestCase):
    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(MEDIA_ROOT, ignore_errors=True)

    def post(self, **data):
        return self.client.post(reverse("note_taking:image_capture"), data)

    def test_reponse_avec_la_reference_a_ecrire(self):
        response = self.post(image=upload())

        self.assertEqual(response.status_code, 201)
        data = response.json()
        self.assertRegex(data["name"], r"^capture-\d{4}-\d{2}-\d{2}-\d{6}\.png$")
        self.assertEqual(data["reference"], f"images/{data['name']}")
        self.assertEqual(data["url"], Image.objects.get(name=data["name"]).file.url)

    def test_aucune_image_envoyee(self):
        response = self.post()

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json(), {"error": "Aucune image reçue."})

    def test_contenu_refuse_avec_le_message_metier(self):
        response = self.post(image=upload(b"pas une image"))

        self.assertEqual(response.status_code, 400)
        self.assertIn("n'est pas une image lisible", response.json()["error"])
        self.assertEqual(Image.objects.count(), 0)

    def test_type_refuse(self):
        response = self.post(image=upload(b"texte", "text/plain", "x.txt"))

        self.assertEqual(response.status_code, 400)
        self.assertIn("text/plain", response.json()["error"])

    def test_lecture_refusee(self):
        response = self.client.get(reverse("note_taking:image_capture"))

        self.assertEqual(response.status_code, 405)

    def test_pas_de_message_dans_l_editeur(self):
        response = self.post(image=upload())

        self.assertEqual(list(get_messages(response.wsgi_request)), [])

    def test_message_de_succes_depuis_la_page_des_images(self):
        """La page se recharge ensuite : le message s'affiche comme les autres."""
        response = self.post(image=upload(), notify="1")

        name = response.json()["name"]
        self.assertEqual(
            [str(m) for m in get_messages(response.wsgi_request)],
            [f"L'image « {name} » est importée."],
        )

    def test_message_de_refus_depuis_la_page_des_images(self):
        response = self.post(image=upload(b"pas une image"), notify="1")

        self.assertEqual(response.status_code, 400)
        self.assertEqual(
            [str(m) for m in get_messages(response.wsgi_request)],
            [response.json()["error"]],
        )


class CapturePagesTests(TestCase):
    def test_page_des_images(self):
        html = self.client.get(reverse("note_taking:images_list")).content.decode()

        self.assertIn('id="image-capture"', html)
        self.assertIn(
            f'data-capture-url="{reverse("note_taking:image_capture")}"', html
        )
        self.assertIn("data-csrf=", html)
        self.assertIn(
            '<script type="module" src="/static/note_taking/images_capture.js">', html
        )

    def test_formulaire_de_note(self):
        html = self.client.get(reverse("note_taking:new_note")).content.decode()

        self.assertIn(
            f'data-capture-url="{reverse("note_taking:image_capture")}"', html
        )
