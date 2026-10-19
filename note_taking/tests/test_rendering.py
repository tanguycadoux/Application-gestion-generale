"""Tests du rendu HTML des notes : note parts et vue Markdown complète."""

from django.test import TestCase
from django.urls import reverse

from note_taking.models import Note, NotePart, Project


class NotePartRenderingTests(TestCase):
    def render(self, content: str) -> str:
        return NotePart(project=Project(name="P"), content=content).rendered_content()

    def test_markdown_simple(self):
        self.assertHTMLEqual(
            self.render("Texte **gras**"), "<p>Texte <strong>gras</strong></p>"
        )

    def test_tableau(self):
        html = self.render("| a | b |\n|---|---|\n| 1 | 2 |")

        self.assertIn("<table>", html)
        self.assertIn("<td>1</td>", html)

    def test_bloc_de_code(self):
        html = self.render("```python\nx = 1\n```")

        self.assertIn('<code class="language-python">x = 1', html)

    def test_attributs_d_image_conserves_apres_le_lien(self):
        html = self.render("![a](image:999){width=50%}")

        self.assertIn("{width=50%}", html)


class NoteMarkdownViewTests(TestCase):
    def test_rendu_du_contenu_complet(self):
        note = Note.objects.create(date="2025-11-24", raw="# P\n\n| a |\n|---|\n| 1 |")

        response = self.client.get(reverse("note_taking:note_md", args=[note.pk]))

        self.assertContains(response, "<h1>P</h1>", html=True)
        self.assertContains(response, "<td>1</td>", html=True)
        self.assertEqual(str(response.context["date"]), "2025-11-24")

    def test_note_sans_contenu(self):
        note = Note.objects.create(date="2025-11-24", raw=None)

        response = self.client.get(reverse("note_taking:note_md", args=[note.pk]))

        self.assertContains(response, "Aucun contenu disponible.")

    def test_note_inexistante(self):
        response = self.client.get(reverse("note_taking:note_md", args=[999]))

        self.assertEqual(response.status_code, 404)
