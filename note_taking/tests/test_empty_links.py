"""Un lien sans texte affiche son adresse, écart voulu à Pandoc (#467)."""

from unittest import expectedFailure

from django.test import TestCase

from note_taking.models import Note
from note_taking.note_outline import outline_sections
from note_taking.rendering import render_note_body, render_passage
from note_taking.tests.links import new_tab_link


class EmptyLinksTests(TestCase):
    @expectedFailure
    def test_adresse_affichee_comme_un_lien_automatique(self):
        for text in (
            "[](https://exemple.org/a_b_c)",
            "[ ](https://exemple.org/a_b_c)",
            "[&nbsp;](https://exemple.org/a_b_c)",
            "[][r]\n\n[r]: https://exemple.org/a_b_c",
            '<a href="https://exemple.org/a_b_c"><em></em></a>',
        ):
            with self.subTest(text=text):
                self.assertIn(
                    new_tab_link(
                        "https://exemple.org/a_b_c", "https://exemple.org/a_b_c"
                    ),
                    render_note_body(text),
                )
        self.assertEqual(
            render_note_body("[](https://exemple.org)"),
            render_note_body("<https://exemple.org>"),
        )

    @expectedFailure
    def test_adresse_echappee(self):
        html = render_note_body("[](https://exemple.org?a=1&b=2)")

        self.assertIn(">https://exemple.org?a=1&amp;b=2<", html)

    @expectedFailure
    def test_adresse_electronique_sans_mailto(self):
        self.assertIn(
            new_tab_link("mailto:a@b.fr", "a@b.fr"),
            render_note_body("[](mailto:a@b.fr)"),
        )

    @expectedFailure
    def test_note_existante(self):
        Note.objects.create(date="2026-03-12", body="x")
        for link in ("2026-03-12", "2026-03-12.qmd", "2026-03-12#ancre"):
            with self.subTest(link=link):
                self.assertIn(
                    ">Note du jeudi 12 mars 2026<", render_note_body(f"[]({link})")
                )

    @expectedFailure
    def test_note_absente(self):
        html = render_note_body("[](2026-03-12)")

        self.assertIn(">Note du jeudi 12 mars 2026<", html)
        self.assertIn("note-link-missing", html)

    @expectedFailure
    def test_date_impossible(self):
        self.assertIn(">2026-13-45<", render_note_body("[](2026-13-45)"))

    @expectedFailure
    def test_ancre_d_un_titre(self):
        html = render_note_body("[](#mon-titre)\n\n# Mon *titre*", heading_ids=True)

        self.assertIn('<a href="#mon-titre">Mon titre</a>', html)

    @expectedFailure
    def test_ancre_absente(self):
        self.assertIn(
            '<a href="#nulle-part">#nulle-part</a>',
            render_note_body("[](#nulle-part)\n\n# Titre", heading_ids=True),
        )

    @expectedFailure
    def test_passage_de_la_recherche(self):
        html = render_passage("# Titre\n\n[](#titre) [](https://exemple.org)", "p-")

        self.assertIn('<a href="#titre">Titre</a>', html)
        self.assertIn(">https://exemple.org<", html)

    def test_identifiant_du_titre_comme_pandoc(self):
        """Le texte ajouté n'entre pas dans l'identifiant : l'ancre de l'export tient."""
        html = render_note_body("# [](https://exemple.org)", heading_ids=True)

        self.assertIn('id="section"', html)

    @expectedFailure
    def test_titre_affiche_dans_le_plan(self):
        html = render_note_body("# [](https://exemple.org)", heading_ids=True)

        self.assertEqual(
            [entry.text for entry in outline_sections(html).entries],
            ["https://exemple.org"],
        )

    def test_non_concernes(self):
        for text, expected in (
            ("[texte](https://exemple.org)", "texte"),
            ("`[](https://exemple.org)`", "<code>[](https://exemple.org)</code>"),
            ("[]()", '<a href=""></a>'),
            ('<a id="repere"></a>', '<a id="repere"></a>'),
        ):
            with self.subTest(text=text):
                self.assertIn(expected, render_note_body(text))

    def test_image_dans_un_lien(self):
        html = render_note_body("[![](image:1)](https://exemple.org)")

        self.assertIn("<img", html)
        self.assertNotIn(">https://exemple.org", html)
