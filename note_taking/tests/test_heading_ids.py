"""Identifiants des titres d'une note (#201) : les liens des résultats de recherche
mènent à la section, comme les identifiants automatiques de Pandoc."""

from django.test import SimpleTestCase, TestCase
from django.urls import reverse

from note_taking.models import Note
from note_taking.rendering import (
    add_heading_ids,
    heading_anchor,
    heading_slug,
    render_note_body,
)


class HeadingSlugTests(SimpleTestCase):
    def test_minuscules_et_tirets(self):
        self.assertEqual(
            heading_slug("Réunion de Préparation"), "réunion-de-préparation"
        )

    def test_ponctuation_retiree_sauf_tiret_souligne_point(self):
        self.assertEqual(heading_slug("A, b: c_d-e.f (g)"), "a-b-c_d-e.f-g")

    def test_chiffres_du_debut_retires(self):
        self.assertEqual(heading_slug("2026 : bilan"), "bilan")

    def test_rien_de_lisible(self):
        self.assertEqual(heading_slug("123 ?"), "section")


class AddHeadingIdsTests(SimpleTestCase):
    def test_id_ajoute(self):
        self.assertEqual(
            add_heading_ids("<h2>Beta</h2><p>x</p>"), '<h2 id="beta">Beta</h2><p>x</p>'
        )

    def test_balises_internes_ignorees_dans_l_id(self):
        self.assertEqual(
            add_heading_ids("<h3>Un <strong>gras</strong></h3>"),
            '<h3 id="un-gras">Un <strong>gras</strong></h3>',
        )

    def test_doublons_numerotes_comme_pandoc(self):
        html = add_heading_ids("<h2>Notes</h2><h2>Notes</h2><h3>Notes</h3>")

        self.assertEqual(
            html,
            '<h2 id="notes">Notes</h2><h2 id="notes-1">Notes</h2>'
            '<h3 id="notes-2">Notes</h3>',
        )

    def test_id_explicite_conserve(self):
        html = add_heading_ids('<h2 id="mon-id">Beta</h2><h2>Mon id</h2>')

        self.assertEqual(html, '<h2 id="mon-id">Beta</h2><h2 id="mon-id-1">Mon id</h2>')

    def test_caracteres_html_decodes(self):
        self.assertIn('id="a-b"', add_heading_ids("<h2>A &amp; B</h2>"))


class HeadingAnchorTests(SimpleTestCase):
    def test_titre_simple(self):
        self.assertEqual(heading_anchor("Réunion"), "réunion")

    def test_titre_avec_mise_en_forme(self):
        self.assertEqual(heading_anchor("Un **gras**"), "un-gras")

    def test_identifiant_explicite(self):
        self.assertEqual(heading_anchor("Réunion {#rt17}"), "rt17")

    def test_titre_vide(self):
        self.assertIsNone(heading_anchor(""))


class NoteBodyIdsTests(TestCase):
    def test_render_note_body_sans_ids_par_defaut(self):
        self.assertNotIn(" id=", render_note_body("# A\n\n## B\n"))

    def test_render_note_body_avec_ids(self):
        html = render_note_body("# A\n\n## B\n", heading_ids=True)

        self.assertIn('<h2 id="a">A</h2>', html)
        self.assertIn('<h3 id="b">B</h3>', html)

    def test_la_page_d_une_note_a_des_ancres(self):
        Note.objects.create(date="2026-10-15", body="# Alpha\n\n## Réunion\n\ntexte\n")

        response = self.client.get(
            reverse("note_taking:note_detail", args=["2026-10-15"])
        )

        self.assertContains(response, 'id="réunion"')
