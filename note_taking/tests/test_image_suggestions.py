"""Liste des images pour l'éditeur : nom à écrire et vignette (#90)."""

from django.test import TestCase
from django.urls import reverse

from images.models import Image


class ImageSuggestionsTests(TestCase):
    def results(self, **params) -> list[dict]:
        response = self.client.get(reverse("note_taking:image_suggestions"), params)
        self.assertEqual(response.status_code, 200)
        return response.json()["results"]

    def test_reference_a_ecrire_et_vignette(self):
        Image.objects.create(name="banc.png", file="note_images/banc.png")

        self.assertEqual(
            self.results(),
            [
                {
                    "name": "banc.png",
                    "reference": "images/banc.png",
                    "url": "/media/note_images/banc.png",
                }
            ],
        )

    def test_triees_par_nom_et_filtrees_sans_tenir_compte_de_la_casse(self):
        for name in ("Schéma.png", "banc.png", "banc-2.svg"):
            Image.objects.create(name=name, file=f"note_images/{name}")

        self.assertEqual(
            [r["name"] for r in self.results()],
            ["banc-2.svg", "banc.png", "Schéma.png"],
        )
        self.assertEqual([r["name"] for r in self.results(q="SCHÉ")], ["Schéma.png"])

    def test_debut_du_nom_avant_le_milieu(self):
        for name in ("a-banc.png", "banc.png"):
            Image.objects.create(name=name, file=f"note_images/{name}")

        self.assertEqual(
            [r["name"] for r in self.results(q="banc")], ["banc.png", "a-banc.png"]
        )

    def test_nombre_limite(self):
        for number in range(60):
            name = f"img{number:02d}.png"
            Image.objects.create(name=name, file=f"note_images/{name}")

        self.assertEqual(len(self.results()), 50)

    def test_lecture_seule(self):
        response = self.client.post(reverse("note_taking:image_suggestions"))

        self.assertEqual(response.status_code, 405)
