"""HTML écrit dans les notes filtré par une liste blanche (#241).

Un script ou un lien `javascript:` dans une note s'exécuterait dans la page et
pourrait envoyer les notes ailleurs : seul le HTML d'un document est gardé.
"""

import unittest

from django.test import SimpleTestCase

from note_taking.rendering import render_markdown


class DangerousHtmlTests(SimpleTestCase):
    @unittest.expectedFailure
    def test_script_retire_avec_son_contenu(self):
        html = render_markdown(
            "Avant\n\n<script>fetch('https://x.org')</script>\n\nAprès"
        )

        self.assertNotIn("<script", html)
        self.assertNotIn("fetch", html)
        self.assertIn("Après", html)

    @unittest.expectedFailure
    def test_gestionnaire_d_evenement_retire(self):
        html = render_markdown(
            '<p onclick="alert(1)">x</p>\n\n![a](/a.png){onerror=alert(1)}'
        )

        self.assertNotIn("onclick", html)
        self.assertNotIn("onerror", html)

    @unittest.expectedFailure
    def test_lien_javascript_retire(self):
        html = render_markdown("[clic](javascript:alert(1))")

        self.assertNotIn("javascript:", html)
        self.assertIn("clic", html)

    @unittest.expectedFailure
    def test_iframe_et_style_retires(self):
        html = render_markdown(
            '<iframe src="https://x.org"></iframe>\n\n<style>p{}</style>\n\n'
            '<span style="position: fixed">x</span>'
        )

        self.assertNotIn("<iframe", html)
        self.assertNotIn("<style", html)
        self.assertNotIn("position", html)

    @unittest.expectedFailure
    def test_image_en_data_retiree(self):
        html = render_markdown('<img src="data:image/svg+xml,&lt;svg&gt;" alt="a">')

        self.assertNotIn("data:", html)


class KeptHtmlTests(SimpleTestCase):
    """Ce que produisent le Markdown et les blocs Quarto reste intact."""

    def test_tableau_aligne(self):
        html = render_markdown("| a | b |\n|:-:|--:|\n| 1 | 2 |")

        self.assertInHTML('<td style="text-align: center;">1</td>', html)
        self.assertInHTML('<td style="text-align: right;">2</td>', html)

    def test_image_avec_attributs(self):
        html = render_markdown("![Banc](/media/banc.png){#fig-banc width=80%}")

        self.assertInHTML(
            '<img alt="Banc" id="fig-banc" src="/media/banc.png" width="80%">', html
        )

    def test_liens_autorises(self):
        html = render_markdown(
            "[web](https://exemple.org) [mail](mailto:a@b.fr) [note](/note_taking/)"
        )

        for href in ("https://exemple.org", "mailto:a@b.fr", "/note_taking/"):
            with self.subTest(href=href):
                self.assertIn(f'href="{href}"', html)
        self.assertNotIn("rel=", html)

    def test_code_avec_langage(self):
        html = render_markdown("```python\nx = '<b>'\n```")

        self.assertIn('<code class="language-python">', html)
        self.assertIn("&lt;b&gt;", html)

    def test_callout_et_colonnes(self):
        html = render_markdown(
            "::: {.callout-note}\nx\n:::\n\n"
            '::: {.columns}\n::: {.column width="40%"}\ny\n:::\n:::'
        )

        self.assertIn('<div class="callout callout-note">', html)
        self.assertIn('<svg xmlns="http://www.w3.org/2000/svg"', html)
        self.assertIn('style="flex: 0 1 40%"', html)
