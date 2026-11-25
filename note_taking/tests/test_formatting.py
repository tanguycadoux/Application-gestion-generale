"""Mise en forme dans l'éditeur et souligné au rendu (#434).

Le JavaScript n'est pas exécuté par les tests : on vérifie ce qu'il promet."""

from pathlib import Path

from django.conf import settings
from django.test import SimpleTestCase

from note_taking.rendering import (
    add_heading_ids,
    remote_images_as_links,
    render_markdown,
    render_plain_markdown,
)

STATIC_DIR = Path(settings.BASE_DIR) / "note_taking" / "static" / "note_taking"


class UnderlineRenderingTests(SimpleTestCase):
    """`[texte]{.underline}`, comme Pandoc et Quarto : `<span class="underline">`."""

    def assertRenders(self, source: str, expected: str) -> None:
        self.assertHTMLEqual(render_markdown(source), expected)

    def test_souligne(self):
        for source in ("[mot]{.underline}", "[mot]{ .underline }"):
            with self.subTest(source=source):
                self.assertRenders(source, '<p><span class="underline">mot</span></p>')

    def test_markdown_dans_le_texte(self):
        self.assertRenders(
            "[**a** `b` [c](https://exemple.fr) [d]]{.underline}",
            '<p><span class="underline"><strong>a</strong> <code>b</code> '
            '<a href="https://exemple.fr">c</a> [d]</span></p>',
        )

    def test_dans_du_markdown(self):
        for source, expected in (
            ("**a [b]{.underline}**", f"<p><strong>a {self.B}</strong></p>"),
            ("[[b]{.underline}](#x)", f'<p><a href="#x">{self.B}</a></p>'),
            ("- [b]{.underline}", f"<ul><li>{self.B}</li></ul>"),
            ("x [b]{.underline}, [b]{.underline}", f"<p>x {self.B}, {self.B}</p>"),
        ):
            with self.subTest(source=source):
                self.assertRenders(source, expected)

    B = '<span class="underline">b</span>'

    def test_legende_d_image(self):
        html = render_plain_markdown("![a [b]{.underline}](/i.png){width=50%}")

        self.assertIn(f"a {self.B}</figcaption>", html)
        self.assertIn('alt="a b"', html)
        self.assertIn('style="width: 50%"', html)

    def test_legende_d_une_image_d_un_autre_site(self):
        source = remote_images_as_links("![a [b]{.underline}](https://x.fr/i.png)")

        self.assertIn(f">a {self.B}</a>", render_plain_markdown(source))

    def test_identifiant_du_titre_sans_la_syntaxe(self):
        html = add_heading_ids(render_plain_markdown("## Le [bilan]{.underline} B"))

        self.assertIn('id="le-bilan-b"', html)

    def test_autres_attributs_en_texte(self):
        """Écart voulu : seule la classe `.underline` est reconnue."""
        for source in (
            "[b]{.autre}",
            "[b]{.underline .autre}",
            "[b]{#id .underline}",
            "[b] {.underline} c",
        ):
            with self.subTest(source=source):
                self.assertNotIn("<span", render_markdown(source))
                self.assertIn("{", render_markdown(source))

    def test_ni_code_ni_formule_ni_echappement(self):
        for source in (
            "`[b]{.underline}`",
            "```\n[b]{.underline}\n```",
            "    [b]{.underline}",
            "\\[b]{.underline}",
            "[b]\\{.underline}",
            "$[b]{.underline}$",
        ):
            with self.subTest(source=source):
                html = render_markdown(source)
                self.assertNotIn('class="underline"', html)
                self.assertIn("[b]{.underline}", html)

    def test_lien_souligne_reste_un_lien(self):
        self.assertRenders(
            "[b](#x){.underline}", '<p><a class="underline" href="#x">b</a></p>'
        )


class FormattingEditorTests(SimpleTestCase):
    def read(self, name: str) -> str:
        return (STATIC_DIR / name).read_text(encoding="utf-8")

    def test_branche_avant_les_raccourcis_de_codemirror(self):
        """Ctrl+I et Ctrl+U y font autre chose (`selectParentSyntax`, `undoSelection`)."""
        script = self.read("editor.js")

        self.assertIn("\n                closeBracketPairs,\n", script)
        self.assertLess(
            script.index("...formattingKeymap"), script.index("...defaultKeymap")
        )

    def test_sous_menu_et_raccourcis(self):
        self.assertIn(
            'label: "Mise en forme", submenu: formattingEntries(view)',
            self.read("editor_menu.js"),
        )
        script = self.read("formatting.js")
        for key in ("B", "I", "U"):
            with self.subTest(key=key):
                self.assertIn(f'shortcut: "Ctrl+{key}"', script)
                self.assertIn(f'key: "Mod-{key.lower()}"', script)

    def test_souligne_ecrit_ce_que_le_rendu_lit(self):
        self.assertIn('"]{.underline}"', self.read("formatting.js"))

    def test_suggestion_remplace_le_crochet_ajoute(self):
        """Sinon `![` complété laisserait `![](images/x)]`."""
        self.assertIn("closedImageEnd(", self.read("suggestions.js"))
