"""Tests du rendu HTML des notes : note parts et vue Markdown complète."""

from django.test import SimpleTestCase, TestCase
from django.urls import reverse

from core.models import Project
from note_taking.models import Note, NotePart
from note_taking.rendering import render_markdown


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


class CalloutRenderingTests(SimpleTestCase):
    def test_titre_en_attribut(self):
        html = render_markdown(
            '::: {.callout-warning title="Attention !"}\nTexte **gras**\n:::'
        )

        self.assertHTMLEqual(
            html,
            '<div class="callout callout-warning">'
            '<div class="callout-header">Attention !</div>'
            '<div class="callout-body"><p>Texte <strong>gras</strong></p></div>'
            "</div>",
        )

    def test_titre_depuis_le_premier_titre_markdown(self):
        html = render_markdown("::: {.callout-tip}\n\n## Mon titre\nTexte\n:::")

        self.assertInHTML('<div class="callout-header">Mon titre</div>', html)
        self.assertNotIn("<h2>", html)

    def test_titre_par_defaut_du_type(self):
        for callout_type, title in (
            ("note", "Note"),
            ("tip", "Astuce"),
            ("warning", "Avertissement"),
            ("caution", "Attention"),
            ("important", "Important"),
        ):
            with self.subTest(callout_type=callout_type):
                html = render_markdown(f"::: {{.callout-{callout_type}}}\nx\n:::")

                self.assertInHTML(f'<div class="callout-header">{title}</div>', html)

    def test_texte_autour_du_callout(self):
        html = render_markdown("Avant\n\n::: {.callout-note}\nDedans\n:::\n\nAprès")

        self.assertHTMLEqual(
            html,
            "<p>Avant</p>"
            '<div class="callout callout-note">'
            '<div class="callout-header">Note</div>'
            '<div class="callout-body"><p>Dedans</p></div>'
            "</div>"
            "<p>Après</p>",
        )

    def test_titre_echappe(self):
        html = render_markdown('::: {.callout-note title="<b>x</b>"}\ny\n:::')

        self.assertIn("&lt;b&gt;x&lt;/b&gt;", html)

    def test_callout_dans_un_bloc_de_code_non_interprete(self):
        html = render_markdown("```\n::: {.callout-note}\nx\n:::\n```")

        self.assertNotIn('class="callout', html)
        self.assertIn("::: {.callout-note}", html)

    def test_callout_non_ferme_laisse_tel_quel(self):
        html = render_markdown("::: {.callout-note}\nx")

        self.assertNotIn('class="callout', html)

    def test_rendu_d_une_note_part(self):
        part = NotePart(
            project=Project(name="P"),
            content='::: {.callout-note title="Remarque"}\nContenu\n:::',
        )

        self.assertInHTML(
            '<div class="callout-header">Remarque</div>', part.rendered_content()
        )


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
