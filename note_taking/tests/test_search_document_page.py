"""La vue « Document » de la recherche, présentée comme la page d'une note (#431)."""

import re

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
            note.date.isoformat(): date_text(note.date, "long")
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

    def test_plan_par_chemin(self):
        plan = self.plan(self.get("path"))

        self.assertEqual([text for _, text in plan], ["Chantier", "Results", "Réunion"])

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

    def test_sections_repliables(self):
        html = self.get("path")

        self.assertEqual(html.count('<section class="note-section"'), 3)
        self.assertIn('data-level="2"', html)

    def test_les_liens_menent_toujours_a_la_note(self):
        note = reverse("note_taking:note_detail", args=["2026-10-01"])

        self.assertIn(f'href="{note}#réunion"', self.get("path"))
        self.assertIn(f'href="{note}"', self.get("date"))

    def test_feuille_et_en_tete_collant(self):
        html = self.get()

        for mark in ("data-note-reading", "data-note-frame", "data-note-content"):
            self.assertIn(mark, html)
        bar = html[html.index("data-reading-bar") :]
        bar = bar[: bar.index("</header>")]
        for label in (
            "<h1",
            "4 passages",
            "Affichage",
            "Regroupement",
            "Trier par",
            "data-outline-slot",
        ):
            self.assertIn(label, bar)
        self.assertIn("note_taking/note_sheet.js", html)
        self.assertIn("note_taking/note_reading.js", html)

    def test_htmx_remplace_le_document_sans_recharger_les_scripts(self):
        html = self.get(headers={"HX-Request": "true"})

        self.assertTrue(self.plan(html))
        self.assertIn("data-note-frame", html)
        self.assertNotIn("<script", html)
        # L'en-tête, hors des résultats, est mis à jour avec eux.
        options = html[html.index('id="results-options" data-hx-swap-oob') :]
        self.assertIn("4 passages", options[: options.index("</nav>")])
        self.assertEqual(html.count("Trier par"), 1)

    def test_sans_resultat_l_en_tete_est_vide(self):
        response = self.client.get(
            self.url,
            {"q": "introuvable", "view": "document"},
            headers={"HX-Request": "true"},
        )

        self.assertContains(response, 'id="results-options"')
        self.assertNotContains(response, "Trier par")

    def test_extraits_inchanges(self):
        html = self.get(view="extraits")

        for mark in ("data-note-reading", "data-reading-bar", "note_reading.js"):
            self.assertNotIn(mark, html)
