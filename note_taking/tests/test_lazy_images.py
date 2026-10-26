"""Images chargées à la demande, quand elles approchent de l'écran (#225)."""

from django.test import SimpleTestCase, TestCase
from django.urls import reverse

from images.models import Image
from note_taking.models import Note
from note_taking.rendering import render_markdown

LAZY = ('loading="lazy"', 'decoding="async"')


class LazyRenderedImagesTests(SimpleTestCase):
    def test_images_du_contenu_rendu(self):
        html = render_markdown("![A](/a.png)\n\n![B](/b.png){width=50%}")

        self.assertEqual(html.count("<img "), 2)
        for attr in LAZY:
            with self.subTest(attr=attr):
                self.assertEqual(html.count(attr), 2)

    def test_texte_sans_image_inchange(self):
        html = render_markdown("`<img>` en code")

        self.assertNotIn("loading=", html)


class LazyPagesTests(TestCase):
    def test_liste_des_images(self):
        Image.objects.create(name="banc.png", file="note_images/banc.png")

        html = self.client.get(reverse("note_taking:images_list")).content.decode()

        for attr in LAZY:
            with self.subTest(attr=attr):
                self.assertIn(attr, html)

    def test_note_complete(self):
        note = Note.objects.create(date="2025-11-24", body="![A](/a.png)")

        html = self.client.get(
            reverse("note_taking:note_md", args=[note.pk])
        ).content.decode()

        for attr in LAZY:
            with self.subTest(attr=attr):
                self.assertIn(attr, html)


class PercentWidthTests(SimpleTestCase):
    """`{width=80%}` en style : l'attribut width n'accepte que des pixels (#259)."""

    def test_largeur_en_pixels_inchangee(self):
        self.assertIn('width="300"', render_markdown("![A](/a.png){width=300}"))
