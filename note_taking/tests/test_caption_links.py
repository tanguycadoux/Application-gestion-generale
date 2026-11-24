"""Un lien ou des crochets dans la légende d'une image (#453)."""

import unittest

from django.test import TestCase

from core.models import Project
from images.models import Image
from note_taking.excerpts import plain_line
from note_taking.models import Note, Passage
from note_taking.qmd.export import note_to_qmd
from note_taking.rendering import render_note_body
from note_taking.services import insert_note_in_table, process_passages
from note_taking.tests.links import new_tab_link
from note_taking.tests.test_body import qmd_file

GUIDE = "https://exemple.org/guide"
CAPTION = f"Vue, voir [le guide]({GUIDE})"
LINK = new_tab_link(GUIDE, "le guide")


class CaptionLinkTests(TestCase):
    def setUp(self):
        self.image = Image.objects.create(name="banc.png", file="note_images/banc.png")

    def analysed(self, body: str) -> Passage:
        note = Note.objects.create(date="2025-11-24", body=f"# P\n\n{body}")
        process_passages(note)
        return note.passages.get()

    @unittest.expectedFailure
    def test_page_de_la_note(self):
        html = render_note_body(f"![{CAPTION}](images/banc.png)")

        self.assertIn(f'src="{self.image.file.url}"', html)
        self.assertIn('alt="Vue, voir le guide"', html)
        self.assertIn(f">Vue, voir {LINK}</figcaption>", html)

    @unittest.expectedFailure
    def test_analyse_et_passage(self):
        passage = self.analysed(f"![{CAPTION}](images/banc.png){{width=50%}}")

        self.assertEqual(list(passage.images.all()), [self.image])
        self.assertEqual(
            passage.content.strip(),
            f"![{CAPTION}](image:{self.image.pk}){{width=50%}}",
        )
        html = passage.rendered_content()
        self.assertIn(f'src="{self.image.file.url}"', html)
        self.assertIn(f">Vue, voir {LINK}</figcaption>", html)

    @unittest.expectedFailure
    def test_crochets_dans_du_code_ou_une_formule(self):
        for caption in ("`mesures[0]`", "$x \\in [0, 1]$", "$x \\in [0, 1[$"):
            with self.subTest(caption=caption):
                html = render_note_body(f"![{caption}](images/banc.png)")

                self.assertIn(f'src="{self.image.file.url}"', html)
                self.assertIn("<figcaption", html)

    @unittest.expectedFailure
    def test_image_distante(self):
        """Elle reste un lien, qui n'en contient pas d'autre."""
        html = render_note_body(f"![{CAPTION}](https://exemple.org/a.png)")

        self.assertIn(
            new_tab_link("https://exemple.org/a.png", "Vue, voir le guide"), html
        )
        self.assertNotIn("<img", html)

    @unittest.expectedFailure
    def test_export_et_reimport(self):
        body = f"# P\n\n![{CAPTION}](images/banc.png)"
        note = Note(date="2025-11-24", body=body.replace("images/", "../autre/"))

        qmd = note_to_qmd(note)
        imported = insert_note_in_table(qmd_file("2025-11-24.qmd", qmd))

        self.assertEqual(imported.body, body)
        self.assertEqual(list(imported.passages.get().images.all()), [self.image])

    @unittest.expectedFailure
    def test_extrait(self):
        self.assertEqual(
            plain_line(f"![{CAPTION}](images/banc.png){{width=50%}} fin"),
            "Vue, voir le guide fin",
        )

    def test_images_qui_se_suivent(self):
        """Le motif s'arrête à la fin de chaque image."""
        html = render_note_body("![A](banc.png) et [un lien](/a) puis ![B](banc.png)")

        self.assertEqual(html.count(f'src="{self.image.file.url}"'), 2)
        self.assertIn(">un lien<", html)


class CaptionNamedAsPathTests(TestCase):
    """Une légende qui reprend le chemin de l'image n'est pas réécrite."""

    def setUp(self):
        self.image = Image.objects.create(name="banc.png", file="note_images/banc.png")
        self.text = "![banc.png](banc.png)"

    @unittest.expectedFailure
    def test_page_de_la_note(self):
        self.assertIn(">banc.png</figcaption>", render_note_body(self.text))

    @unittest.expectedFailure
    def test_passage(self):
        note = Note.objects.create(date="2025-11-24", body=f"# P\n{self.text}")
        process_passages(note)

        self.assertEqual(
            note.passages.get().content, f"![banc.png](image:{self.image.pk})"
        )

    @unittest.expectedFailure
    def test_export(self):
        qmd = note_to_qmd(Note(date="2025-11-24", body=self.text))

        self.assertTrue(qmd.endswith("![banc.png](images/banc.png)"))

    def test_passage_sans_base(self):
        part = Passage(
            project=Project(name="P"), content=f"![banc.png](image:{self.image.pk})"
        )

        self.assertIn(">banc.png</figcaption>", part.rendered_content())
