"""La vue « Document » de la recherche, présentée comme la page d'une note (#431)."""

import re
import unittest

from django.test import SimpleTestCase, TestCase
from django.urls import reverse

from core.dates import date_text
from note_taking.models import Note
from note_taking.rendering import add_heading_ids
from note_taking.services import process_passages

NOTES = {
    "2026-10-01": """# Chantier

Ouverture.

## Réunion

Point un, [voir](#réunion).

## Results

Mesures.
""",
    "2026-10-15": """# Chantier

## Réunion

Point deux.
""",
}


class HeadingPrefixTests(SimpleTestCase):
    @unittest.expectedFailure
    def test_prefixe_des_identifiants(self):
        self.assertEqual(
            add_heading_ids("<h2>Notes</h2><h3>Notes</h3>", prefix="doc-"),
            '<h2 id="doc-notes">Notes</h2><h3 id="doc-notes-1">Notes</h3>',
        )


class DocumentPageTests(TestCase):
    url = reverse("note_taking:notes_search")

    @classmethod
    def setUpTestData(cls):
        for day, body in NOTES.items():
            process_passages(Note.objects.create(date=day, body=body))
        cls.titles = {
            note.date.isoformat(): f"Note du {date_text(note.date, 'long')}"
            for note in Note.objects.all()
        }

    def get(self, group="date", view="document", **options) -> str:
        response = self.client.get(
            self.url, {"q": "projet:Chantier", "view": view, "group": group}, **options
        )
        return response.content.decode()

    def plan(self, html: str) -> list[tuple[str, str]]:
        """Les entrées du plan : identifiant visé, texte."""
        nav = re.search(
            r'<nav [^>]*aria-label="Plan du document".*?</nav>', html, re.DOTALL
        )
        assert nav is not None
        return re.findall(r'<a href="#([^"]+)"[^>]*>([^<]*)</a>', nav[0])

    @unittest.expectedFailure
    def test_plan_par_date(self):
        plan = self.plan(self.get("date"))

        self.assertEqual(
            [text for _, text in plan],
            [
                self.titles["2026-10-15"],
                "Chantier",
                "Réunion",
                self.titles["2026-10-01"],
                "Chantier",
                "Réunion",
                "Results",
            ],
        )

    @unittest.expectedFailure
    def test_plan_par_chemin(self):
        plan = self.plan(self.get("path"))

        self.assertEqual([text for _, text in plan], ["Chantier", "Results", "Réunion"])

    @unittest.expectedFailure
    def test_identifiants_uniques_dans_toute_la_page(self):
        """Un titre répété d'une note à l'autre, ou du nom d'un élément de la page
        (`results`)."""
        for group in ("date", "path"):
            with self.subTest(group=group):
                html = self.get(group)
                ids = re.findall(r'\sid="([^"]+)"', html)
                self.assertEqual(sorted(ids), sorted(set(ids)))
                for target, _ in self.plan(html):
                    self.assertIn(target, ids)

    @unittest.expectedFailure
    def test_sections_repliables(self):
        html = self.get("path")

        self.assertEqual(html.count('<section class="note-section"'), 3)
        self.assertIn('data-level="2"', html)

    def test_les_liens_menent_toujours_a_la_note(self):
        note = reverse("note_taking:note_detail", args=["2026-10-01"])

        self.assertIn(f'href="{note}#réunion"', self.get("path"))
        self.assertIn(f'href="{note}"', self.get("date"))

    @unittest.expectedFailure
    def test_feuille_et_barre_collante(self):
        html = self.get()

        for mark in ("data-note-reading", "data-note-frame", "data-note-content"):
            self.assertIn(mark, html)
        bar = html[html.index("data-reading-bar") :]
        bar = bar[: bar.index("data-note-reading")]
        for label in ("Affichage", "Regroupement", "Trier par", "data-outline-slot"):
            self.assertIn(label, bar)
        self.assertIn("note_taking/note_sheet.js", html)
        self.assertIn("note_taking/note_reading.js", html)

    @unittest.expectedFailure
    def test_htmx_remplace_le_document_sans_recharger_les_scripts(self):
        html = self.get(headers={"HX-Request": "true"})

        self.assertTrue(self.plan(html))
        self.assertIn("data-note-frame", html)
        self.assertNotIn("<script", html)

    def test_extraits_inchanges(self):
        html = self.get(view="extraits")

        for mark in ("data-note-reading", "data-reading-bar", "note_reading.js"):
            self.assertNotIn(mark, html)
