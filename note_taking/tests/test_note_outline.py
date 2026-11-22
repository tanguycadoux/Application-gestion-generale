"""Plan de la note en lecture et sections repliables (#404)."""

import re

from django.test import SimpleTestCase, TestCase
from django.urls import reverse

from note_taking.models import Note
from note_taking.note_outline import OutlineEntry, outline_sections


class OutlineSectionsTests(SimpleTestCase):
    def test_sections_imbriquees_par_niveau(self):
        html = (
            '<p>intro</p><h2 id="a">A</h2><p>1</p><h3 id="b">B</h3><p>2</p>'
            '<h2 id="c">C</h2><p>3</p>'
        )

        layout = outline_sections(html)

        self.assertEqual(
            layout.html,
            '<p>intro</p><section class="note-section" data-level="2">'
            '<h2 id="a">A</h2><div class="note-section-body" id="section-body-1">'
            '<p>1</p><section class="note-section" data-level="3">'
            '<h3 id="b">B</h3><div class="note-section-body" id="section-body-2">'
            "<p>2</p></div></section></div></section>"
            '<section class="note-section" data-level="2"><h2 id="c">C</h2>'
            '<div class="note-section-body" id="section-body-3"><p>3</p>'
            "</div></section>",
        )

    def test_plan(self):
        layout = outline_sections(
            '<h2 id="a">Un <strong>gras</strong> &amp; co</h2><h4 id="b">B</h4>'
        )

        self.assertEqual(
            layout.entries,
            [OutlineEntry(2, "Un gras & co", "a"), OutlineEntry(4, "B", "b")],
        )

    def test_niveau_saute_ferme_correctement(self):
        layout = outline_sections('<h4 id="a">A</h4><p>x</p><h2 id="b">B</h2>')

        self.assertEqual(layout.html.count("<section"), 2)
        self.assertEqual(layout.html.count("</section>"), 2)
        self.assertLess(layout.html.index("</section>"), layout.html.index('id="b"'))

    def test_titre_dans_un_bloc_non_replie(self):
        """Un titre dans un encadré ne peut pas ouvrir une section qui en sortirait."""
        html = '<h2 id="a">A</h2><div class="callout"><h3 id="b">B</h3></div><p>x</p>'

        layout = outline_sections(html)

        self.assertEqual(layout.html.count("<section"), 1)
        self.assertIn(
            '<div class="callout"><h3 id="b">B</h3></div><p>x</p></div>', layout.html
        )
        self.assertEqual([entry.id for entry in layout.entries], ["a"])

    def test_elements_vides_et_attributs(self):
        html = '<h2 id="a">A</h2><p>x<br>y<img src="i.png" alt="&gt;"></p><h2 id="b">B</h2>'

        layout = outline_sections(html)

        self.assertEqual(layout.html.count("<section"), 2)
        self.assertIn('alt="&gt;"></p></div></section><section', layout.html)

    def test_sans_titre(self):
        layout = outline_sections("<p>x</p>")

        self.assertEqual(layout.html, "<p>x</p>")
        self.assertEqual(layout.entries, [])

    def test_titre_sans_identifiant_hors_du_plan(self):
        layout = outline_sections("<h2>A</h2><p>x</p>")

        self.assertEqual(layout.entries, [])
        self.assertEqual(layout.html, "<h2>A</h2><p>x</p>")


class NoteDetailOutlineTests(TestCase):
    def get(self, body):
        note = Note.objects.create(date="2026-11-22", body=body)
        return self.client.get(reverse("note_taking:note_detail", args=[note.date]))

    def test_plan_affiche_sans_javascript(self):
        html = self.get("# Projet\n\nx\n\n## Réunion\n\ny\n").content.decode()

        nav = re.search(r'<nav [^>]*aria-label="Plan de la note".*?</nav>', html, re.S)
        self.assertIsNotNone(nav)
        self.assertIn('href="#projet"', nav.group())
        self.assertIn('href="#réunion"', nav.group())
        self.assertNotRegex(nav.group(0), r"<nav [^>]*\shidden[\s>=]")

    def test_sections_repliables_dans_la_page(self):
        html = self.get("# Projet\n\nx\n\n## Réunion\n\ny\n").content.decode()

        self.assertIn('<section class="note-section" data-level="2">', html)
        self.assertIn('<section class="note-section" data-level="3">', html)

    def test_bouton_du_plan_et_script(self):
        response = self.get("# Projet\n\nx\n")

        self.assertContains(response, "note_taking/note_reading.js")
        # Cloné par le script, comme dans l'éditeur : rien d'inerte sans JavaScript.
        self.assertContains(response, '<template id="outline-toggle">')

    def test_note_sans_titre_sans_plan(self):
        response = self.get("Texte seul.\n")

        self.assertNotContains(response, 'aria-label="Plan de la note"')

    def test_note_vide(self):
        response = self.get("")

        self.assertContains(response, "Cette note est vide.")
        self.assertNotContains(response, 'aria-label="Plan de la note"')
