"""Numéros des tableaux et figures, et références `@tbl-…` / `@fig-…` (#278).

Les numéros repartent de 1 à chaque rendu et suivent l'ordre du texte, comme
dans un document Quarto (1.10.19 : « Table 1: », « Figure 1: », même avec
`lang: fr`).
"""

from django.test import SimpleTestCase, TestCase

from core.models import Project
from note_taking.models import NotePart
from note_taking.rendering import number_floats, render_markdown, render_note_body

TABLE = "| a |\n|---|\n| 1 |"
NBSP = "\xa0"


def render(text: str) -> str:
    return number_floats(render_markdown(text))


class TableNumberTests(SimpleTestCase):
    def test_tableau_a_identifiant_numerote(self):
        html = render(f"{TABLE}\n\n: Premier {{#tbl-a}}")

        self.assertIn(f"<caption>Table{NBSP}1: Premier</caption>", html)

    def test_numeros_dans_l_ordre_du_texte(self):
        html = render(f"{TABLE}\n\n: A {{#tbl-a}}\n\n{TABLE}\n\n: B {{#tbl-b}}")

        self.assertIn(f"Table{NBSP}1: A", html)
        self.assertIn(f"Table{NBSP}2: B", html)

    def test_tableau_sans_identifiant_non_numerote(self):
        html = render(f"{TABLE}\n\n: Libre")

        self.assertIn("<caption>Libre</caption>", html)
        self.assertNotIn("Table&nbsp;", html)
        self.assertNotIn(f"Table{NBSP}", html)

    def test_tableau_sans_legende_non_numerote(self):
        self.assertNotIn(f"Table{NBSP}", render(TABLE))


class FigureNumberTests(SimpleTestCase):
    def test_image_a_identifiant_devient_une_figure_numerotee(self):
        html = render("![Banc de mesure](banc.png){#fig-banc}")

        self.assertHTMLEqual(
            html,
            '<figure class="my-2" id="fig-banc">'
            '<img loading="lazy" decoding="async" alt="Banc de mesure" src="banc.png">'
            '<figcaption class="mt-2 text-sm text-center text-slate-600">'
            f"Figure{NBSP}1: Banc de mesure</figcaption></figure>",
        )

    def test_image_sans_identifiant_inchangee(self):
        html = render("![Banc](banc.png)")

        self.assertNotIn("<figure", html)
        self.assertIn('alt="Banc"', html)

    def test_image_a_identifiant_sans_legende_numerotee_sans_texte(self):
        """Quarto : « Figure 1 », sans deux-points."""
        html = render("![](banc.png){#fig-banc}")

        self.assertIn(f">Figure{NBSP}1</figcaption>", html)

    def test_figure_en_colonnes_sans_legende_numerotee_sans_texte(self):
        html = render("::: {#fig-banc layout-ncol=2}\n![A](a.png)\n\n![B](b.png)\n:::")

        self.assertIn(f">Figure{NBSP}1</figcaption></figure>", html)

    def test_figure_en_colonnes_numerotee(self):
        html = render(
            "::: {#fig-banc layout-ncol=2}\n![A](a.png)\n\n![B](b.png)\n\nLégende\n:::"
        )

        self.assertIn(f"Figure{NBSP}1: ", html)
        self.assertIn("Légende", html)

    def test_images_d_une_figure_en_colonnes_restent_des_images(self):
        html = render(
            "::: {#fig-banc layout-ncol=2}\n![A](a.png){#fig-a}\n\n![B](b.png)\n\nLégende\n:::"
        )

        self.assertEqual(html.count("<figure"), 1)
        self.assertEqual(html.count("<figcaption"), 1)

    def test_figures_et_tableaux_comptes_separement(self):
        html = render(
            f"![F1](a.png){{#fig-a}}\n\n{TABLE}\n\n: T1 {{#tbl-a}}\n\n![F2](b.png){{#fig-b}}"
        )

        self.assertIn(f"Figure{NBSP}1: F1", html)
        self.assertIn(f"Table{NBSP}1: T1", html)
        self.assertIn(f"Figure{NBSP}2: F2", html)

    def test_legende_echappee(self):
        html = render("![a < b & c](a.png){#fig-a}")

        self.assertIn("a &lt; b &amp; c</figcaption>", html)


class ReferenceTests(SimpleTestCase):
    def test_reference_en_lien_numerote(self):
        html = render(f"Voir @tbl-a.\n\n{TABLE}\n\n: A {{#tbl-a}}")

        self.assertIn(f'<a href="#tbl-a" class="quarto-xref">Table{NBSP}1</a>.', html)

    def test_reference_avant_la_cible(self):
        html = render(
            "Voir @fig-b puis @fig-a.\n\n![A](a.png){#fig-a}\n\n![B](b.png){#fig-b}"
        )

        self.assertIn(f'<a href="#fig-b" class="quarto-xref">Figure{NBSP}2</a>', html)
        self.assertIn(f'<a href="#fig-a" class="quarto-xref">Figure{NBSP}1</a>', html)

    def test_reference_inconnue_comme_quarto(self):
        html = render("Voir @tbl-absent.")

        self.assertIn("<strong>?@tbl-absent</strong>", html)

    def test_reference_dans_un_bloc_de_code_inchangee(self):
        html = render("`@fig-a` et\n\n```\n@fig-a\n```\n\n![A](a.png){#fig-a}")

        self.assertIn("<code>@fig-a</code>", html)
        self.assertIn("<pre><code>@fig-a", html)

    def test_adresse_electronique_inchangee(self):
        html = render("écrire à nom@fig-a.fr")

        self.assertNotIn("quarto-xref", html)
        self.assertNotIn("?@", html)

    def test_autre_arobase_inchangee(self):
        html = render("Voir @dupont et @sec-x")

        self.assertNotIn("quarto-xref", html)

    def test_reference_dans_un_lien_inchangee(self):
        html = render("[voir @fig-a](https://exemple.org)\n\n![A](a.png){#fig-a}")

        self.assertIn('<a href="https://exemple.org">voir @fig-a</a>', html)


class RenderContextTests(TestCase):
    """Les numéros dépendent du texte rendu : note entière ou note part seule."""

    BODY = "# P\n\n![A](a.png){#fig-a}\n\n## S\n\nVoir @fig-b.\n\n![B](b.png){#fig-b}"

    def test_note_entiere_numerotee_depuis_un(self):
        html = render_note_body(self.BODY)

        self.assertIn(f"Figure{NBSP}1: A", html)
        self.assertIn(f"Figure{NBSP}2: B", html)
        self.assertIn(f'class="quarto-xref">Figure{NBSP}2</a>', html)

    def test_note_part_repart_de_un(self):
        part = NotePart(
            project=Project(name="P"), content="Voir @fig-b.\n\n![B](b.png){#fig-b}"
        )

        html = part.rendered_content()

        self.assertIn(f"Figure{NBSP}1: B", html)
        self.assertIn(f'class="quarto-xref">Figure{NBSP}1</a>', html)

    def test_reference_hors_de_la_note_part_comme_quarto(self):
        part = NotePart(project=Project(name="P"), content="Voir @fig-a.")

        self.assertIn("<strong>?@fig-a</strong>", part.rendered_content())

    def test_titres_toujours_decales(self):
        self.assertIn("<h2>P</h2>", render_note_body(self.BODY))
