"""Tests du rendu HTML des notes : note parts et vue Markdown complète."""

import unittest

from django.contrib.staticfiles import finders
from django.test import SimpleTestCase, TestCase
from django.urls import reverse

from core.models import Project
from note_taking.models import Note, NotePart
from note_taking.rendering import IMAGE_MISSING_PATH, render_markdown


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

    def test_largeur_d_image_appliquee(self):
        html = self.render("![a](image:999){width=50%}")

        self.assertIn('width="50%"', html)
        self.assertNotIn("{width", html)

    def test_identifiant_de_figure_applique(self):
        html = self.render("![a](image:999){#fig-banc}")

        self.assertIn('id="fig-banc"', html)
        self.assertNotIn("{#fig", html)


class ImageMissingTests(SimpleTestCase):
    """L'image de remplacement d'une image supprimée existe dans les statiques (#55)."""

    def test_image_de_remplacement_presente(self):
        self.assertIsNotNone(finders.find(IMAGE_MISSING_PATH))


class CalloutRenderingTests(SimpleTestCase):
    @unittest.expectedFailure
    def test_titre_en_attribut(self):
        html = render_markdown(
            '::: {.callout-warning title="Attention !"}\nTexte **gras**\n:::'
        )

        self.assertHTMLEqual(
            html,
            '<div class="callout callout-warning">'
            '<div class="callout-header">'
            '<span class="material-symbols-rounded callout-icon" aria-hidden="true">warning</span>'
            '<span class="callout-title">Attention !</span>'
            "</div>"
            '<div class="callout-body"><p>Texte <strong>gras</strong></p></div>'
            "</div>",
        )

    @unittest.expectedFailure
    def test_titre_depuis_le_premier_titre_markdown(self):
        html = render_markdown("::: {.callout-tip}\n\n## Mon titre\nTexte\n:::")

        self.assertInHTML('<span class="callout-title">Mon titre</span>', html)
        self.assertNotIn("<h2>", html)

    @unittest.expectedFailure
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

                self.assertInHTML(f'<span class="callout-title">{title}</span>', html)

    @unittest.expectedFailure
    def test_texte_autour_du_callout(self):
        html = render_markdown("Avant\n\n::: {.callout-note}\nDedans\n:::\n\nAprès")

        self.assertHTMLEqual(
            html,
            "<p>Avant</p>"
            '<div class="callout callout-note">'
            '<div class="callout-header">'
            '<span class="material-symbols-rounded callout-icon" aria-hidden="true">info</span>'
            '<span class="callout-title">Note</span>'
            "</div>"
            '<div class="callout-body"><p>Dedans</p></div>'
            "</div>"
            "<p>Après</p>",
        )

    @unittest.expectedFailure
    def test_icone_par_type(self):
        for callout_type, icon in (
            ("note", "info"),
            ("tip", "lightbulb"),
            ("warning", "warning"),
            ("caution", "report"),
            ("important", "error"),
        ):
            with self.subTest(callout_type=callout_type):
                html = render_markdown(f"::: {{.callout-{callout_type}}}\nx\n:::")

                self.assertInHTML(
                    '<span class="material-symbols-rounded callout-icon"'
                    f' aria-hidden="true">{icon}</span>',
                    html,
                )

    def test_sans_icone_avec_icon_false(self):
        html = render_markdown("::: {.callout-note icon=false}\nx\n:::")

        self.assertNotIn("callout-icon", html)

    def test_sans_icone_pour_un_type_inconnu(self):
        html = render_markdown("::: {.callout-autre}\nx\n:::")

        self.assertIn('class="callout callout-autre"', html)
        self.assertNotIn("callout-icon", html)

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

    @unittest.expectedFailure
    def test_rendu_d_une_note_part(self):
        part = NotePart(
            project=Project(name="P"),
            content='::: {.callout-note title="Remarque"}\nContenu\n:::',
        )

        self.assertInHTML(
            '<span class="callout-title">Remarque</span>', part.rendered_content()
        )


class NoteMarkdownViewTests(TestCase):
    def test_rendu_du_contenu_complet(self):
        note = Note.objects.create(date="2025-11-24", body="# P\n\n| a |\n|---|\n| 1 |")

        response = self.client.get(reverse("note_taking:note_md", args=[note.pk]))

        self.assertContains(response, "<h1>P</h1>", html=True)
        self.assertContains(response, "<td>1</td>", html=True)
        self.assertEqual(str(response.context["date"]), "2025-11-24")

    def test_note_sans_contenu(self):
        note = Note.objects.create(date="2025-11-24", body="")

        response = self.client.get(reverse("note_taking:note_md", args=[note.pk]))

        self.assertContains(response, "Aucun contenu disponible.")

    def test_note_inexistante(self):
        response = self.client.get(reverse("note_taking:note_md", args=[999]))

        self.assertEqual(response.status_code, 404)
