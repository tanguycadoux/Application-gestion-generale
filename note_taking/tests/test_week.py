"""Les notes d'une semaine, groupées par projet (#208)."""

import re

from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from note_taking.models import Note
from note_taking.services import process_passages


def text(html: str) -> str:
    return " ".join(re.sub(r"<[^>]+>", " ", html).split())


class WeekNotesTests(TestCase):
    def note(self, day: str, body: str) -> Note:
        note = Note.objects.create(date=day, body=body)
        process_passages(note)
        return note

    def html(self) -> str:
        response = self.client.get("/week/2025-W48/")
        self.assertEqual(response.status_code, 200)
        return response.content.decode()

    def groups(self) -> list[tuple[str, list[str]]]:
        """Chaque projet, et ses notes telles qu'on les lit."""
        html = self.html()
        block = html.split('id="week-block-1"')[1].split('id="week-block-2"')[0]
        return [
            (
                text(part.split("</h3>")[0].split(">", 1)[1]),
                [
                    text(found)
                    for found in re.findall(r"<a [^>]*>(<time.*?</time>)</a>", part)
                ],
            )
            for part in block.split("<h3")[1:]
        ]

    def url(self, anchor: str = "") -> str:
        return reverse("note_taking:note_detail", args=["2025-11-24"]) + anchor

    def test_groupees_par_projet_puis_par_date(self):
        self.note("2025-11-25", "# Beta\nx\n# Alpha\ny")
        self.note("2025-11-24", "# Alpha\nz")

        self.assertEqual(
            self.groups(),
            [
                ("Alpha", ["lundi 24 novembre 2025", "mardi 25 novembre 2025"]),
                ("Beta", ["mardi 25 novembre 2025"]),
            ],
        )

    def test_bornes_de_la_semaine_comprises(self):
        for day in ("2025-11-23", "2025-11-24", "2025-11-30", "2025-12-01"):
            self.note(day, "# P\nx")

        self.assertEqual(
            self.groups(),
            [("P", ["lundi 24 novembre 2025", "dimanche 30 novembre 2025"])],
        )

    def test_chemins_ecrits_avec_leur_lien(self):
        self.note("2025-11-24", "# P\nx\n## A {#a-1}\ny\n### B\nz\n## A\nw")

        html = self.html()

        self.assertIn(f'href="{self.url("#a-1")}">A</a>', html)
        self.assertIn(f'href="{self.url("#b")}">A › B</a>', html)
        # Un chemin répété dans la note une seule fois.
        self.assertEqual(html.count(">A</a>"), 1)

    def test_niveau_sans_texte_omis(self):
        self.note("2025-11-24", "# P\n## A\n### B\nz")

        html = self.html()

        self.assertNotIn(">A</a>", html)
        self.assertIn(">A › B</a>", html)

    def test_note_ouverte_a_son_projet(self):
        self.note("2025-11-24", "# P\nx\n# Q\n## A\ny")

        self.assertIn(f'href="{self.url("#q")}"><time', self.html())

    def test_texte_sans_projet_a_la_fin(self):
        self.note("2025-11-24", "libre\n# P\nx")

        self.assertEqual([name for name, _ in self.groups()], ["P", "Sans projet"])

    def test_note_vide(self):
        self.note("2025-11-24", "")

        self.assertEqual(self.groups(), [("Sans projet", ["lundi 24 novembre 2025"])])

    def test_titre_echappe(self):
        self.note("2025-11-24", "# P\n## R&D <b>\nx")

        self.assertIn("R&amp;D &lt;b&gt;</a>", self.html())

    def test_nombre_de_requetes_constant(self):
        def count() -> int:
            with CaptureQueriesContext(connection) as captured:
                self.html()
            return len(captured)

        self.note("2025-11-24", "# P\nx")
        before = count()
        for day in range(25, 30):
            self.note(f"2025-11-{day}", f"# P{day}\nx\n## A\ny\n### B\nz")

        self.assertEqual(count(), before)
