"""Les liens d'une note s'ouvrent dans un nouvel onglet (#438)."""

from django.test import TestCase
from django.urls import reverse

from note_taking.models import Note
from note_taking.note_outline import outline_sections
from note_taking.rendering import note_heading_ids, render_note_body
from note_taking.rendering.new_tab import HIDDEN_TEXT, ICON
from note_taking.tests.links import new_tab_link


class NewTabLinksTests(TestCase):
    def test_liens_qui_quittent_la_page(self):
        for text, href, label in (
            ("[site](https://exemple.org)", "https://exemple.org", "site"),
            (
                "[**gras** et `code`](http://exemple.org)",
                "http://exemple.org",
                "<strong>gras</strong> et <code>code</code>",
            ),
            ("[écrire](mailto:a@b.fr)", "mailto:a@b.fr", "écrire"),
        ):
            with self.subTest(text=text):
                self.assertIn(new_tab_link(href, label), render_note_body(text))

    def test_liens_dans_les_blocs(self):
        link = new_tab_link("https://exemple.org", "site")
        for block in (
            "::: {.callout-note}\n{}\n:::",
            "- {}",
            "> {}",
            "| T |\n|---|\n| {} |",
        ):
            with self.subTest(block=block):
                html = render_note_body(
                    block.replace("{}", "[site](https://exemple.org)")
                )
                self.assertIn(link, html)

    def test_liens_dans_la_page(self):
        html = render_note_body(
            "# Titre\n\n[plan](#titre), @fig-a, [vide]()\n\n![A](a.png){#fig-a}"
        )

        self.assertIn('<a href="#titre">plan</a>', html)
        self.assertIn('<a href="#fig-a" class="quarto-xref">', html)
        self.assertNotIn("target=", html)
        self.assertNotIn("nouvel onglet", html)

    def test_target_et_rel_ecrits_retires(self):
        html = render_note_body(
            '<a href="#x" target="_blank" rel="opener">a</a> '
            '[b](https://exemple.org){target="_top" rel="opener"}'
        )

        self.assertIn('<a href="#x">a</a>', html)
        self.assertIn(new_tab_link("https://exemple.org", "b"), html)
        self.assertNotIn("opener", html.replace("noopener", ""))
        self.assertNotIn("_top", html)

    def test_image_seule_dans_un_lien_sans_fleche(self):
        html = render_note_body("[![A](/a.png)](https://exemple.org)")

        self.assertIn('target="_blank"', html)
        self.assertNotIn(ICON, html)
        self.assertIn(f"{HIDDEN_TEXT}</a>", html)

    def test_attribut_avec_un_chevron(self):
        html = render_note_body('[a](https://exemple.org "x > y")')

        self.assertEqual(html.count('target="_blank"'), 1)
        self.assertIn(f">a{ICON}", html)

    def test_code_inchange(self):
        html = render_note_body('`<a href="https://exemple.org">a</a>`')

        self.assertNotIn("target=", html)

    def test_titre_avec_un_lien(self):
        """Ni l'identifiant, ni le plan, ni l'ancre d'un passage n'ont la marque."""
        body = "# P\n\n## Voir [le site](https://exemple.org)\n\nx"

        entries = outline_sections(render_note_body(body, heading_ids=True)).entries

        self.assertEqual(
            [(entry.text, entry.id) for entry in entries],
            [("P", "p"), ("Voir le site", "voir-le-site")],
        )
        self.assertEqual(
            note_heading_ids(body, ["P", "Voir [le site](https://exemple.org)"]),
            ["p", "voir-le-site"],
        )


class NewTabLinksPagesTests(TestCase):
    """Partout où le rendu des notes sert."""

    def setUp(self):
        self.client.post(
            reverse("note_taking:new_note"),
            {"date": "2025-11-24", "body": "# P\n\nVoir [site](https://exemple.org)."},
        )
        self.link = new_tab_link("https://exemple.org", "site")

    def test_page_de_la_note(self):
        note = Note.objects.get()

        response = self.client.get(reverse("note_taking:note_detail", args=[note.date]))

        self.assertContains(response, self.link)

    def test_passage(self):
        self.assertIn(self.link, Note.objects.get().passages.get().rendered_content())

    def test_vue_document_de_la_recherche(self):
        response = self.client.get(
            reverse("note_taking:notes_search"), {"q": "site", "view": "document"}
        )

        self.assertContains(response, self.link)
