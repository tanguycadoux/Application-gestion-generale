"""Renommer un niveau de chemin : réécrire les titres des notes (#299).

Un titre est repéré par la suite des titres au-dessus de lui, projet compris, pas par
son niveau.
"""

from django.test import SimpleTestCase, TestCase

from core.models import Project, Section
from core.sections import levels
from note_taking.exceptions import NoteRenameError
from note_taking.models import Note
from note_taking.renaming import (
    find_headings,
    find_occurrences,
    headings,
    rename_titles,
    rewrite_titles,
)
from note_taking.services import process_note_parts


class HeadingsTests(SimpleTestCase):
    def test_projet_chemin_et_ligne(self):
        found = headings("intro\n# P\n## S\ntexte\n### T")

        self.assertEqual(
            [(h.number, h.level, h.title, h.project, h.path) for h in found],
            [
                (2, 1, "P", "P", ()),
                (3, 2, "S", "P", ("S",)),
                (5, 3, "T", "P", ("S", "T")),
            ],
        )

    def test_un_titre_moins_profond_efface_les_plus_profonds(self):
        found = headings("# P\n## S\n### T\n## U\n### V")

        self.assertEqual([h.path for h in found][-2:], [("U",), ("U", "V")])

    def test_niveau_saute(self):
        self.assertEqual(headings("# P\n### T")[-1].path, ("T",))

    def test_code_callout_et_sept_dieses_ignores(self):
        body = (
            "# P\n```\n## code\n```\n"
            '::: {.callout-note title="t"}\n## callout\n:::\n####### trop\n## vrai'
        )

        self.assertEqual([h.title for h in headings(body)], ["P", "vrai"])

    def test_texte_avant_le_projet(self):
        found = headings("## S\n# P")

        self.assertEqual((found[0].project, found[0].path), (None, ("S",)))


class FindHeadingsTests(SimpleTestCase):
    def numbers(self, body: str, levels_: list[str], project: str = "P") -> list[int]:
        return [h.number for h in find_headings(body, project, levels_)]

    def test_le_niveau_et_pas_ses_descendants(self):
        body = "# P\n## S\n### T\ntexte\n## S\n"

        self.assertEqual(self.numbers(body, ["S"]), [2, 5])
        self.assertEqual(self.numbers(body, ["S", "T"]), [3])

    def test_le_meme_niveau_a_un_autre_niveau_de_titre(self):
        """`### S` sans `##` au-dessus est le même niveau que `## S` (#305)."""
        self.assertEqual(self.numbers("# P\n## S\n# P\n### S", ["S"]), [2, 4])

    def test_casse_et_espaces_ignores(self):
        self.assertEqual(
            self.numbers("# P\n##   réunion  d'avancement ", ["Réunion d'avancement"]),
            [2],
        )

    def test_meme_nom_sous_un_autre_parent(self):
        body = "# P\n## A\n### S\n## B\n### S"

        self.assertEqual(self.numbers(body, ["A", "S"]), [3])
        self.assertEqual(self.numbers(body, ["B", "S"]), [5])

    def test_autre_projet(self):
        body = "# P\n## S\n# Q\n## S"

        self.assertEqual(self.numbers(body, ["S"], project="Q"), [4])

    def test_nom_du_projet_a_la_casse_exacte(self):
        self.assertEqual(self.numbers("# p\n## S", ["S"], project="P"), [])

    def test_aucun_titre(self):
        self.assertEqual(self.numbers("# P\n## S", ["X"]), [])


class RewriteTitlesTests(SimpleTestCase):
    def test_titre_reecrit_le_reste_inchange(self):
        self.assertEqual(
            rewrite_titles("# P\n## Ancien\ntexte Ancien\n", [2], "Nouveau"),
            "# P\n## Nouveau\ntexte Ancien\n",
        )

    def test_dieses_espaces_et_fin_de_ligne_windows_gardes(self):
        self.assertEqual(
            rewrite_titles("# P\r\n###   Ancien  \r\ntexte\r\n", [2], "Nouveau"),
            "# P\r\n###   Nouveau  \r\ntexte\r\n",
        )

    def test_titre_indente(self):
        self.assertEqual(
            rewrite_titles("# P\n  ## Ancien", [2], "Nouveau"), "# P\n  ## Nouveau"
        )

    def test_le_texte_entier_du_titre_est_remplace(self):
        """Les attributs d'un titre en font partie : c'est le nom du niveau."""
        self.assertEqual(
            rewrite_titles("# P\n## Ancien {#id}", [2], "Nouveau"), "# P\n## Nouveau"
        )

    def test_plusieurs_titres(self):
        body = "# P\n## A\n### x\n## A"

        self.assertEqual(rewrite_titles(body, [2, 4], "B"), "# P\n## B\n### x\n## B")

    def test_aucun_numero(self):
        self.assertEqual(rewrite_titles("# P\n## A", [], "B"), "# P\n## A")


class RenameTitlesTests(TestCase):
    def setUp(self):
        self.project = Project.objects.create(name="P")

    def note(self, body: str, day: str = "2025-11-24") -> Note:
        note = Note.objects.create(date=day, body=body)
        process_note_parts(note)
        return note

    def section(self, *names: str) -> Section:
        return Section.objects.get(name=names[-1])

    def test_occurrences_du_bilan(self):
        first = self.note("# P\n## Réunion\nx\n### Suite\ny")
        self.note("# P\n### Réunion\nz", day="2025-11-25")

        found = find_occurrences(self.project, ["Réunion"])

        self.assertEqual(
            [(o.key.split(":")[1], o.where, o.chain) for o in found],
            [
                ("2", "Note du 24 novembre 2025, ligne 2", "P › Réunion"),
                ("2", "Note du 25 novembre 2025, ligne 2", "P › Réunion"),
            ],
        )
        self.assertEqual(found[0].key, f"{first.pk}:2")

    def test_titres_choisis_reecrits_et_notes_recalculees(self):
        note = self.note("# P\n## Réunion\nx\n### Suite\ny")
        [occurrence] = find_occurrences(self.project, ["Réunion"])

        report = rename_titles(self.project, ["Réunion"], "Rencontre", [occurrence.key])

        note.refresh_from_db()
        self.assertEqual(note.body, "# P\n## Rencontre\nx\n### Suite\ny")
        self.assertEqual(
            sorted(levels(part.section) for part in note.parts.all() if part.section),
            [["Rencontre"], ["Rencontre", "Suite"]],
        )
        self.assertEqual(report, ["1 titre réécrit dans 1 note."])

    def test_compte_rendu_au_pluriel(self):
        self.note("# P\n## A\nx\n## A\ny")
        self.note("# P\n## A\nz", day="2025-11-25")
        keys = [o.key for o in find_occurrences(self.project, ["A"])]

        report = rename_titles(self.project, ["A"], "B", keys)

        self.assertEqual(report, ["3 titres réécrits dans 2 notes."])

    def test_seuls_les_titres_choisis(self):
        first = self.note("# P\n## A\nx")
        second = self.note("# P\n## A\ny", day="2025-11-25")
        keep, rename = (o.key for o in find_occurrences(self.project, ["A"]))

        rename_titles(self.project, ["A"], "B", [rename])

        first.refresh_from_db()
        second.refresh_from_db()
        self.assertEqual((first.body, second.body), ("# P\n## A\nx", "# P\n## B\ny"))
        self.assertEqual(
            sorted(Section.objects.values_list("name", flat=True)), ["A", "B"]
        )
        self.assertEqual(keep, f"{first.pk}:2")

    def test_note_changee_depuis_le_bilan_rien_n_est_ecrit(self):
        first = self.note("# P\n## A\nx")
        second = self.note("# P\n## A\ny", day="2025-11-25")
        keys = [o.key for o in find_occurrences(self.project, ["A"])]
        second.body = "# P\n## Autre\ny"
        second.save()

        with self.assertRaisesMessage(NoteRenameError, "Une note a changé"):
            rename_titles(self.project, ["A"], "B", keys)

        first.refresh_from_db()
        self.assertEqual(first.body, "# P\n## A\nx")

    def test_rien_n_est_ecrit_si_une_note_echoue(self):
        """Atomique : l'erreur d'une note annule les précédentes."""
        first = self.note("# P\n## A\nx")
        second = self.note("# P\n## A\ny", day="2025-11-25")
        keys = [o.key for o in find_occurrences(self.project, ["A"])]
        second.body = "# P\n## A\n![a](absente.png)"
        second.save()

        with self.assertRaises(Exception):  # noqa: B017, PT011 - l'image manque
            rename_titles(self.project, ["A"], "B", keys)

        first.refresh_from_db()
        self.assertEqual(first.body, "# P\n## A\nx")

    def test_sans_titre_choisi(self):
        self.note("# P\n## A\nx")

        self.assertEqual(
            rename_titles(self.project, ["A"], "B", []),
            ["0 titre réécrit dans 0 note."],
        )
