"""Figures implicites de Pandoc (#422) : une image seule dans son paragraphe, avec un
texte, est une figure dont ce texte est la légende."""

from django.test import SimpleTestCase, TestCase
from django.urls import reverse

from images.models import Image
from note_taking.models import Note
from note_taking.rendering import number_floats, render_markdown

NBSP = "\xa0"


def render(text: str) -> str:
    return number_floats(render_markdown(text))


class ImplicitFigureTests(SimpleTestCase):
    def test_image_seule_avec_texte(self):
        html = render("![Vue d'ensemble](a.png)")

        self.assertHTMLEqual(
            html,
            '<figure class="my-2">'
            '<img loading="lazy" decoding="async" alt="Vue d\'ensemble" src="a.png">'
            '<figcaption class="mt-2 text-sm text-center text-slate-600">'
            "Vue d'ensemble</figcaption></figure>",
        )

    def test_sans_numero_ni_place_dans_la_numerotation(self):
        html = render("![Libre](a.png)\n\n![Banc](b.png){#fig-banc}")

        self.assertIn(">Libre</figcaption>", html)
        self.assertIn(f">Figure{NBSP}1: Banc</figcaption>", html)

    def test_pas_de_figure(self):
        for text in (
            "![](a.png)",
            "![ ](a.png)",
            "Voir ![A](a.png)",
            "![A](a.png) ici",
            "![A](a.png)\n![B](b.png)",
            "[![A](a.png)](https://exemple.org)",
            "- ![A](a.png)",
            "| T |\n|---|\n| ![A](a.png) |",
        ):
            with self.subTest(text=text):
                html = render(text)
                self.assertNotIn("<figure", html)
                self.assertNotIn("<figcaption", html)
                self.assertIn("<img", html)

    def test_image_par_reference(self):
        html = render("![Banc][b]\n\n[b]: a.png")

        self.assertIn('alt="Banc" src="a.png"', html)
        self.assertIn(">Banc</figcaption>", html)

    def test_legende_en_markdown_alt_en_texte(self):
        html = render("![Un **banc** à $x^2$, H<sub>2</sub>O &lt; 3](a.png)")

        self.assertIn(
            '>Un <strong>banc</strong> à <span class="math inline">\\(x^2\\)</span>, '
            "H<sub>2</sub>O &lt; 3</figcaption>",
            html,
        )
        self.assertIn('alt="Un banc à \\(x^2\\), H2O &lt; 3"', html)

    def test_fig_alt(self):
        html = render('![Légende](a.png){fig-alt="Un banc"}')

        self.assertIn('alt="Un banc"', html)
        self.assertIn(">Légende</figcaption>", html)

    def test_legende_filtree(self):
        html = render('![a <script>alert(1)</script> <b onclick="x()">b</b>](a.png)')

        self.assertNotIn("script", html)
        self.assertNotIn("onclick", html)


class ImplicitFigurePageTests(TestCase):
    """Le même rendu sur la page de la note et dans un passage."""

    def setUp(self):
        image = Image.objects.create(name="a.png", file="note_images/a.png")
        self.client.post(
            reverse("note_taking:new_note"),
            {"date": "2025-11-24", "body": "# P\n\n![Vue d'ensemble](img/a.png)"},
        )
        self.note = Note.objects.get()
        self.caption = ">Vue d'ensemble</figcaption>"
        self.src = image.file.url

    def test_page_de_la_note(self):
        response = self.client.get(
            reverse("note_taking:note_detail", args=[self.note.date])
        )

        self.assertContains(response, self.caption)
        self.assertContains(response, f'src="{self.src}"')

    def test_passage(self):
        html = self.note.passages.get().rendered_content()

        self.assertIn(self.caption, html)
        self.assertIn(f'src="{self.src}"', html)
