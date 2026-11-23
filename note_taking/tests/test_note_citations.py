"""Notes qui citent une note (#207) : liens portés par les passages, recalculés à
chaque enregistrement, et listés sur la page de la note citée."""

from datetime import date
from io import StringIO

from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse

from note_taking.models import Note, PassageNoteLink
from note_taking.note_citations import citations
from note_taking.services import process_passages


def note(day: str, body: str) -> Note:
    created = Note.objects.create(date=day, body=body)
    process_passages(created)
    return created


class PassageNoteLinksTests(TestCase):
    def test_liens_portes_par_le_passage(self):
        source = note(
            "2026-03-14",
            "[a](2026-03-10.qmd)\n# P\n## A\n[b](2026-03-12.qmd#x)\n## B\n"
            "[c](2026-03-12.qmd) [d](2026-03-12.qmd)",
        )

        self.assertEqual(
            sorted(
                PassageNoteLink.objects.filter(passage__note=source).values_list(
                    "passage__heading_path", "target_date", "anchor"
                )
            ),
            [
                ("", date(2026, 3, 10), ""),
                ("P › A", date(2026, 3, 12), "x"),
                ("P › B", date(2026, 3, 12), ""),
            ],
        )

    def test_liens_recalcules(self):
        source = note("2026-03-14", "# P\n[a](2026-03-12.qmd)")

        source.body = "# P\n[a](2026-03-13.qmd)"
        process_passages(source)

        self.assertEqual(
            list(PassageNoteLink.objects.values_list("target_date", flat=True)),
            [date(2026, 3, 13)],
        )

    def test_reprocess_notes_recalcule_les_liens(self):
        source = note("2026-03-14", "# P\n[a](2026-03-12.qmd)")
        PassageNoteLink.objects.all().delete()

        call_command("reprocess_notes", stdout=StringIO())

        self.assertEqual(
            list(
                PassageNoteLink.objects.values_list("passage__note", "target_date")
            ),
            [(source.pk, date(2026, 3, 12))],
        )


class CitationsTests(TestCase):
    def setUp(self):
        self.cited = note("2026-03-12", "# P\nx")

    def test_notes_qui_citent(self):
        note("2026-03-13", "# Alpha\n## Suivi\nVoir [la veille](2026-03-12.qmd).")
        note("2026-03-15", "Avant tout titre : [ici](2026-03-12.qmd#p).")
        note("2026-03-16", "# Beta\n[ailleurs](2026-03-01.qmd)")

        found = citations(self.cited)

        self.assertEqual(
            [
                (str(c.passage.note.date), c.passage.heading_path, c.excerpt)
                for c in found
            ],
            [
                ("2026-03-15", "", "Avant tout titre : ici."),
                ("2026-03-13", "Alpha › Suivi", "Voir la veille."),
            ],
        )
        self.assertEqual(
            found[1].url,
            reverse("note_taking:note_detail", args=["2026-03-13"]) + "#suivi",
        )
        self.assertEqual(
            found[0].url, reverse("note_taking:note_detail", args=["2026-03-15"])
        )

    def test_un_passage_qui_cite_deux_fois_compte_une_fois(self):
        note("2026-03-13", "# A\n[a](2026-03-12.qmd) et [b](2026-03-12.qmd#p)")

        self.assertEqual(len(citations(self.cited)), 1)

    def test_la_note_ne_se_cite_pas_elle_meme(self):
        self.cited.body = "# P\n[ici](2026-03-12.qmd#p)"
        process_passages(self.cited)

        self.assertEqual(citations(self.cited), [])

    def test_extrait_court(self):
        note("2026-03-13", "# A\n- " + "mot " * 80 + "[a](2026-03-12.qmd)")

        excerpt = citations(self.cited)[0].excerpt

        self.assertLessEqual(len(excerpt), 160)
        self.assertTrue(excerpt.startswith("mot mot"))
        self.assertTrue(excerpt.endswith("…"))

    def test_note_creee_apres_le_lien(self):
        note("2026-03-13", "# A\n[demain](2026-03-14.qmd)")

        created = note("2026-03-14", "# B\ny")

        self.assertEqual(len(citations(created)), 1)


class CitationsPageTests(TestCase):
    def test_liste_sur_la_page(self):
        cited = note("2026-03-12", "# P\nx")
        note("2026-03-13", "# Alpha\n## Suivi\nVoir [la veille](2026-03-12.qmd).")

        response = self.client.get(
            reverse("note_taking:note_detail", args=[cited.date])
        )

        self.assertContains(response, "Citée par")
        self.assertContains(response, "Voir la veille.")
        self.assertContains(response, "Alpha › Suivi")
        self.assertContains(
            response,
            f'href="{reverse("note_taking:note_detail", args=["2026-03-13"])}#suivi"',
        )

    def test_rien_sans_citation(self):
        cited = note("2026-03-12", "# P\nx")

        response = self.client.get(
            reverse("note_taking:note_detail", args=[cited.date])
        )

        self.assertNotContains(response, "Citée par")
