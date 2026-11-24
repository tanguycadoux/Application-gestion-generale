"""Aucune image d'un autre serveur n'est chargée, quelle que soit son écriture (#458)."""

import re
import unittest

from django.test import TestCase
from django.urls import reverse

from images.models import Image
from note_taking.models import Note
from note_taking.rendering import render_markdown, render_note_body
from note_taking.services import process_passages

URL = "https://exemple.org/a.png"
# Chaque écriture d'une image distante, sans le motif `![…](https://…)` déjà traité.
WRITINGS = {
    "titre entre apostrophes": f"![Logo]({URL} 't')",
    "espace": "![Logo](https://exemple.org/a b.png)",
    "référence": f"![Logo][r]\n\n[r]: {URL}",
    "référence courte": f"![Logo]\n\n[Logo]: {URL}",
    "sans schéma": "![Logo](//exemple.org/a.png)",
    "HTML": f'<img src="{URL}" alt="Logo">',
    "HTML sans schéma": '<img alt="Logo" src="//exemple.org/a.png">',
    "HTML en majuscules": '<IMG SRC="HTTPS://exemple.org/a.png" alt="Logo">',
    "barres obliques inverses": r'<img src="\\exemple.org/a.png" alt="Logo">',
    "barre oblique puis inverse": r'<img src="/\exemple.org/a.png" alt="Logo">',
    "tabulation dans l'adresse": '<img src="/&#9;/exemple.org/a.png" alt="Logo">',
    "espace avant l'adresse": f'<img src=" {URL}" alt="Logo">',
    "chevron dans un attribut": f'<img title="a > b" src="{URL}" alt="Logo">',
}


class RemoteImageTests(TestCase):
    def assertNoImage(self, html: str) -> None:
        self.assertNotRegex(html, r"(?i)<img\b")

    @unittest.expectedFailure
    def test_lien_au_lieu_de_l_image(self):
        for name, text in WRITINGS.items():
            for where in ("{}", "::: {{.callout-note}}\n{}\n:::", "- {}"):
                with self.subTest(writing=name, where=where):
                    html = render_note_body(where.format(text))

                    self.assertNoImage(html)
                    self.assertRegex(html, r"<a [^>]*exemple\.org[^>]*>Logo<")

    @unittest.expectedFailure
    def test_dans_un_passage(self):
        for name, text in WRITINGS.items():
            with self.subTest(writing=name):
                Note.objects.all().delete()
                note = Note.objects.create(date="2025-11-24", body=f"# P\n\n{text}")
                process_passages(note)

                self.assertNoImage(note.passages.get().rendered_content())

    @unittest.expectedFailure
    def test_ni_figure_ni_legende(self):
        """Une image distante n'est jamais une figure implicite (#422)."""
        html = render_note_body(WRITINGS["référence"])

        self.assertNotIn("<figure", html)
        self.assertNotIn("<figcaption", html)

    @unittest.expectedFailure
    def test_dans_un_lien_son_texte_seul(self):
        html = render_markdown(
            f'<a href="https://exemple.org"><img src="{URL}" alt="Logo"></a>'
        )

        self.assertEqual(
            re.sub(r"\s", "", html), '<p><ahref="https://exemple.org">Logo</a></p>'
        )

    @unittest.expectedFailure
    def test_sans_texte_l_adresse(self):
        html = render_markdown(f'<img src="{URL}">')

        self.assertIn(f'<a href="{URL}">{URL}</a>', html)

    @unittest.expectedFailure
    def test_texte_echappe(self):
        html = render_markdown(
            f'<img src="{URL}?a=1&b=2" alt="&lt;script&gt;alert(1)&lt;/script&gt;">'
        )

        self.assertNoImage(html)
        self.assertNotIn("<script", html)
        self.assertIn("&lt;script&gt;", html)
        self.assertIn('?a=1&amp;b=2"', html)

    def test_image_locale_inchangee(self):
        Image.objects.create(name="banc.png", file="note_images/banc.png")
        for text in (
            "![Banc](images/banc.png)",
            '<img src="/media/note_images/banc.png" alt="Banc">',
            '<img src="banc.png" alt="Banc">',
        ):
            with self.subTest(text=text):
                self.assertIn("<img ", render_note_body(text))

    def test_code_inchange(self):
        self.assertIn("&lt;img", render_markdown(f'`<img src="{URL}">`'))


class ContentSecurityPolicyTests(TestCase):
    @unittest.expectedFailure
    def test_images_de_l_application_seulement(self):
        """Seconde barrière : le navigateur refuse une image d'un autre serveur."""
        response = self.client.get(reverse("note_taking:new_note"))

        self.assertIn(
            "img-src 'self' data:", response.headers["Content-Security-Policy"]
        )
