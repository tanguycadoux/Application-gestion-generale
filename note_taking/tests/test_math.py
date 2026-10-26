"""Formules LaTeX $…$ et $$…$$ comme dans Quarto (#99).

Le rendu garde la formule telle qu'écrite, dans un élément `math` (forme de
Pandoc avec `--mathjax`, celle de Quarto) ; KaTeX, embarqué en local, l'affiche
dans le navigateur.
"""

import re

from django.contrib.staticfiles import finders
from django.test import SimpleTestCase, TestCase
from django.urls import reverse

from note_taking.rendering import render_markdown

ALIGNED = "\\begin{aligned}\nE_i &= E_z\\\\\nE_j &= E_x\n\\end{aligned}"


def inline(tex: str) -> str:
    return f'<span class="math inline">\\({tex}\\)</span>'


def display(tex: str) -> str:
    return f'<span class="math display">\\[{tex}\\]</span>'


class MathRenderingTests(SimpleTestCase):
    def test_formule_en_ligne(self):
        self.assertHTMLEqual(
            render_markdown("a $x^2$ b"), f"<p>a {inline('x^2')} b</p>"
        )

    def test_formule_en_bloc(self):
        self.assertHTMLEqual(
            render_markdown("$$x = \\frac{1}{2}$$"),
            f"<p>{display('x = \\frac{1}{2}')}</p>",
        )

    def test_formule_en_bloc_sur_plusieurs_lignes_intacte(self):
        html = render_markdown(f"On a :\n\n$$\n{ALIGNED}\n$$")

        self.assertIn(display(f"\n{ALIGNED}\n").replace("&", "&amp;"), html)

    def test_formule_non_interpretee_en_markdown(self):
        tex = "a_1 * b_2 * c^2^ ~d~ \\{x\\} \\alpha"

        self.assertIn(inline(tex), render_markdown(f"${tex}$"))

    def test_caracteres_html_echappes(self):
        self.assertIn(inline("a &lt; b"), render_markdown("$a < b$"))

    def test_formules_qui_se_suivent(self):
        self.assertHTMLEqual(
            render_markdown("$x$$y$"), f"<p>{inline('x')}{inline('y')}</p>"
        )

    def test_dollars_sans_formule(self):
        for text in (
            "a $ y$ b",
            "a $z $ b",
            "Prix 5$ et 6$",
            "de $5 à $6",
            "-np $SLURM -i a\n-np $SLURM -i b",
        ):
            with self.subTest(text=text):
                self.assertNotIn("math", render_markdown(text))

    def test_formule_suivie_d_un_chiffre(self):
        self.assertHTMLEqual(render_markdown("$a$1"), "<p>$a$1</p>")

    def test_dollar_echappe(self):
        self.assertHTMLEqual(render_markdown("\\$x$"), "<p>$x$</p>")

    def test_dans_un_tableau_et_une_liste(self):
        for text in (
            "| $a_1$ | x |\n|---|---|\n| 1 | 2 |",
            "- $a_1$ dans une liste",
        ):
            with self.subTest(text=text):
                self.assertIn(inline("a_1"), render_markdown(text))


# Polices citées par la feuille de KaTeX : url(fonts/KaTeX_Main-Regular.woff2)
FONT_URL_REGEX = re.compile(r"url\(fonts/(?P<name>[\w-]+\.woff2)\)")


class KatexAssetsTests(TestCase):
    """KaTeX embarqué en local (#217), chargé une fois par les pages de notes."""

    def test_katex_embarque_avec_licence_et_readme(self):
        for name in ("katex.min.js", "katex.min.css", "LICENSE", "README.md"):
            with self.subTest(name=name):
                self.assertIsNotNone(finders.find(f"vendor/katex/{name}"))

    def test_polices_woff2_presentes(self):
        css_path = finders.find("vendor/katex/katex.min.css")
        self.assertIsNotNone(css_path)
        with open(css_path, encoding="utf-8") as css:
            fonts = set(FONT_URL_REGEX.findall(css.read()))

        self.assertTrue(fonts)
        for name in fonts:
            with self.subTest(name=name):
                self.assertIsNotNone(finders.find(f"vendor/katex/fonts/{name}"))

    def test_charge_une_fois_sur_les_pages_de_notes(self):
        html = self.client.get(reverse("note_taking:index")).content.decode()

        for tag in (
            '<link rel="stylesheet" href="/static/vendor/katex/katex.min.css">',
            '<script src="/static/vendor/katex/katex.min.js" defer></script>',
            '<script src="/static/note_taking/math.js" defer></script>',
        ):
            with self.subTest(tag=tag):
                self.assertEqual(html.count(tag), 1)

    def test_pas_charge_hors_des_notes(self):
        html = self.client.get(reverse("todolist:index")).content.decode()

        self.assertNotIn("katex", html)
