"""La page d'une note affiche le texte tel qu'écrit ; les note parts sont un index (#234)."""

from django.test import TestCase
from django.urls import reverse

from note_taking.models import Note
from note_taking.services import process_note_parts

BODY = """Introduction avant tout titre.

# Beta

Texte de Beta.

## Suite

::: {.metadata}
tags: [m1]
:::

Texte de la suite.

# Alpha

Texte d'Alpha.
"""


class NotePageTests(TestCase):
    def setUp(self):
        self.note = Note.objects.create(date="2025-11-24", body=BODY)
        process_note_parts(self.note)
        self.html = self.client.get(
            reverse("note_taking:note_detail", args=[self.note.date])
        ).content.decode()

    def test_texte_dans_l_ordre_ecrit(self):
        positions = [
            self.html.index(text)
            for text in (
                "Introduction avant tout titre.",
                "Texte de Beta.",
                "Texte de la suite.",
                "Texte d&#x27;Alpha." if "&#x27;" in self.html else "Texte d'Alpha.",
            )
        ]

        self.assertEqual(positions, sorted(positions))

    def test_titres_du_texte_sous_le_titre_de_la_page(self):
        self.assertInHTML('<h2 id="beta">Beta</h2>', self.html)
        self.assertInHTML('<h3 id="suite">Suite</h3>', self.html)
        self.assertEqual(self.html.count("<h1"), 1)

    def test_tags_du_bloc_de_metadonnees_en_pastille(self):
        self.assertIn(">m1</li>", self.html)
        self.assertNotIn("{.metadata}", self.html)

    def test_actions_conservees(self):
        for name in ("export_note", "edit_note", "delete_note"):
            self.assertIn(
                reverse(f"note_taking:{name}", args=[self.note.date]), self.html
            )
