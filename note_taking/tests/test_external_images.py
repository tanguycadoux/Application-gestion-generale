"""Images externes et chemins d'images (#220).

Une image externe ne fait pas échouer l'analyse, et ne se charge pas : elle
s'affiche comme un lien vers son adresse (aucune requête vers l'extérieur).
Le nom d'une image importée se tire de son chemin de la même façon partout.
"""

from django.test import SimpleTestCase, TestCase
from django.urls import reverse

from core.models import Project
from images.models import Image
from note_taking.models import Note, NotePart
from note_taking.qmd.export import note_to_qmd
from note_taking.rendering import image_name
from note_taking.services import process_note_parts

URL = "https://example.com/logo.png"


class ExternalImageAnalysisTests(TestCase):
    def test_image_externe_analysee(self):
        note = Note.objects.create(date="2025-11-24", body=f"# P\n![Logo]({URL})")

        process_note_parts(note)

        part = note.parts.get()
        self.assertEqual(part.content, f"![Logo]({URL})")
        self.assertFalse(part.images.exists())

    def test_chemin_avec_antislash(self):
        image = Image.objects.create(name="banc.png", file="note_images/banc.png")
        note = Note.objects.create(
            date="2025-11-24", body="# P\n![Banc](images\\banc.png)"
        )

        process_note_parts(note)

        self.assertEqual(list(note.parts.get().images.all()), [image])


class ExternalImageRenderingTests(TestCase):
    def render_part(self, content: str) -> str:
        return NotePart(project=Project(name="P"), content=content).rendered_content()

    def test_note_part_lien_au_lieu_de_l_image(self):
        html = self.render_part(f"![Logo]({URL})")

        self.assertInHTML(f'<a href="{URL}">Logo</a>', html)
        self.assertNotIn("<img", html)

    def test_legende_vide_lien_sur_l_adresse(self):
        html = self.render_part(f"![]({URL})")

        self.assertInHTML(f'<a href="{URL}">{URL}</a>', html)

    def test_note_complete_lien_au_lieu_de_l_image(self):
        note = Note.objects.create(date="2025-11-24", body=f"![Logo]({URL})")

        response = self.client.get(reverse("note_taking:note_md", args=[note.pk]))

        self.assertContains(response, f'<a href="{URL}">Logo</a>', html=True)
        self.assertNotContains(response, f'src="{URL}"')

    def test_export_garde_l_image_externe(self):
        note = Note(date="2025-11-24", body=f"![Logo]({URL})")

        self.assertIn(f"![Logo]({URL})", note_to_qmd(note))


class ImageNameTests(SimpleTestCase):
    """Une seule règle, pour l'analyse, le rendu et l'export."""

    def test_nom_tire_du_chemin(self):
        for path, expected in (
            ("banc.png", "banc.png"),
            ("images/banc.png", "banc.png"),
            ("images\\sous\\banc.png", "banc.png"),
            (URL, None),
            ("http://example.com/a.png", None),
        ):
            with self.subTest(path=path):
                self.assertEqual(image_name(path), expected)
