"""Tests de la page de détail d'une image et de la grille des images (#84)."""

from django.test import TestCase
from django.urls import reverse

from core.models import Project
from images.models import Image
from note_taking.models import Note, NotePart, NotePartImageLink


def use_image(image: Image, note_date: str) -> Note:
    note = Note.objects.get_or_create(date=note_date)[0]
    part = NotePart.objects.create(
        note=note, project=Project.objects.get_or_create(name="P")[0]
    )
    NotePartImageLink.objects.create(note_part=part, image=image)
    return note


class ImageDetailTests(TestCase):
    def setUp(self):
        self.image = Image.objects.create(name="banc.png", file="note_images/banc.png")

    def get(self, image: Image | None = None):
        image = image or self.image
        return self.client.get(reverse("note_taking:image_detail", args=[image.pk]))

    def test_image_et_nom(self):
        response = self.get()

        self.assertContains(response, "<figure", status_code=200)
        self.assertContains(response, f'src="{self.image.file.url}"')
        self.assertContains(response, 'alt="banc.png"')
        self.assertContains(response, "<figcaption")

    def test_notes_qui_utilisent_l_image(self):
        later = use_image(self.image, "2026-02-03")
        earlier = use_image(self.image, "2025-11-24")
        use_image(self.image, "2025-11-24")  # deux note parts de la même note

        html = self.get().content.decode()

        for note in (earlier, later):
            with self.subTest(note=note):
                self.assertIn(
                    f'href="{reverse("note_taking:note_detail", args=[note.pk])}"', html
                )
        self.assertEqual(html.count('<time datetime="2025-11-24"'), 1)
        self.assertLess(
            html.index('datetime="2025-11-24"'), html.index('datetime="2026-02-03"')
        )

    def test_image_inutilisee(self):
        response = self.get()

        self.assertContains(response, "Aucune note n'utilise cette image.")

    def test_image_inexistante(self):
        response = self.client.get(reverse("note_taking:image_detail", args=[999]))

        self.assertEqual(response.status_code, 404)


class ImageGridTests(TestCase):
    def test_chaque_image_mene_a_sa_page(self):
        image = Image.objects.create(name="banc.png", file="note_images/banc.png")

        response = self.client.get(reverse("note_taking:images_list"))

        self.assertContains(
            response, f'href="{reverse("note_taking:image_detail", args=[image.pk])}"'
        )

    def test_grille_en_liste_avec_plus_de_colonnes(self):
        Image.objects.create(name="banc.png", file="note_images/banc.png")

        response = self.client.get(reverse("note_taking:images_list"))

        self.assertContains(response, 'role="list"')
        self.assertContains(response, "minmax(180px,1fr)")
        self.assertContains(response, "<figure")
