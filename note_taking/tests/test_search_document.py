"""Assemblage des résultats en un document Markdown (#356) : sans accès à la base."""

from datetime import date

from django.test import SimpleTestCase

from note_taking.search_document import DocPart, assemble, split_titles


def part(day, titles, content, project="Alpha"):
    iso = date(2026, 10, day).isoformat()
    return DocPart(
        date=date(2026, 10, day),
        date_label=f"{day} octobre 2026",
        note_url=f"/notes/{iso}/",
        part_url=f"/notes/{iso}/#ancre",
        titles=tuple(titles),
        content=content,
        project=project,
    )


class SplitTitlesTests(SimpleTestCase):
    def test_titres_du_projet_au_plus_profond(self):
        self.assertEqual(
            split_titles("Alpha › Réunion › Bilan"), ("Alpha", "Réunion", "Bilan")
        )

    def test_vide(self):
        self.assertEqual(split_titles(""), ())


class ByDateTests(SimpleTestCase):
    def test_une_note_part(self):
        text = assemble([part(15, ["Alpha", "Réunion"], "texte")], "date")

        self.assertEqual(
            text,
            "## [Note du 15 octobre 2026](/notes/2026-10-15/)\n\n"
            "### Alpha\n\n#### Réunion\n\ntexte\n",
        )

    def test_titre_deja_ouvert_pas_repete(self):
        text = assemble(
            [
                part(15, ["Alpha", "Réunion"], "un"),
                part(15, ["Alpha", "Réunion"], "deux"),
                part(15, ["Alpha", "Bilan"], "trois"),
            ],
            "date",
        )

        self.assertEqual(text.count("### Alpha"), 1)
        self.assertEqual(text.count("#### Réunion"), 1)
        self.assertIn("#### Bilan\n\ntrois", text)
        self.assertLess(text.index("un"), text.index("deux"))

    def test_retour_a_un_niveau_plus_haut_reecrit_son_titre(self):
        text = assemble(
            [
                part(15, ["Alpha", "A", "B"], "profond"),
                part(15, ["Alpha", "A"], "direct"),
            ],
            "date",
        )

        self.assertEqual(text.count("#### A"), 2)
        self.assertLess(text.index("profond"), text.rindex("#### A"))

    def test_branches_qui_divergent(self):
        text = assemble(
            [
                part(15, ["Alpha", "A", "B"], "x"),
                part(15, ["Alpha", "A", "C"], "y"),
            ],
            "date",
        )

        self.assertEqual(text.count("#### A"), 1)
        self.assertIn("##### B\n\nx\n\n##### C\n\ny", text)

    def test_les_notes_les_plus_recentes_d_abord_et_titres_rouverts(self):
        text = assemble(
            [part(10, ["Alpha"], "ancien"), part(15, ["Alpha"], "recent")], "date"
        )

        self.assertLess(text.index("15 octobre"), text.index("10 octobre"))
        self.assertEqual(text.count("### Alpha"), 2)

    def test_niveaux_limites_a_six(self):
        titles = ["P", "a", "b", "c", "d", "e"]

        text = assemble([part(15, titles, "x")], "date")

        self.assertIn("###### d\n", text)
        self.assertIn("###### e\n", text)
        self.assertNotIn("#######", text)

    def test_sans_titres(self):
        text = assemble([part(15, [], "texte")], "date")

        self.assertEqual(
            text, "## [Note du 15 octobre 2026](/notes/2026-10-15/)\n\ntexte\n"
        )

    def test_rien(self):
        self.assertEqual(assemble([], "date"), "")


class ByPathTests(SimpleTestCase):
    def test_une_note_part(self):
        text = assemble([part(15, ["Alpha", "Réunion"], "texte")], "path")

        self.assertEqual(
            text,
            "## Alpha\n\n### Réunion\n\n"
            "**[15 octobre 2026](/notes/2026-10-15/#ancre)**\n\ntexte\n",
        )

    def test_les_notes_d_un_meme_chemin_sous_un_seul_titre(self):
        text = assemble(
            [
                part(10, ["Alpha", "Réunion"], "ancien"),
                part(15, ["Alpha", "Réunion"], "recent"),
            ],
            "path",
        )

        self.assertEqual(text.count("### Réunion"), 1)
        self.assertEqual(text.count("## Alpha"), 1)
        self.assertLess(text.index("recent"), text.index("ancien"))

    def test_chemins_tries_sans_casse(self):
        text = assemble(
            [
                part(15, ["beta"], "b", project="beta"),
                part(15, ["Alpha", "z"], "a1"),
                part(15, ["Alpha", "Éa"], "a2"),
            ],
            "path",
        )

        self.assertLess(text.index("## Alpha"), text.index("## beta"))
        self.assertLess(text.index("### Éa"), text.index("### z"))

    def test_parent_et_enfants_sous_le_meme_titre(self):
        text = assemble(
            [
                part(15, ["Alpha", "A", "B"], "profond"),
                part(15, ["Alpha", "A"], "direct"),
            ],
            "path",
        )

        self.assertEqual(text.count("### A"), 1)
        self.assertLess(text.index("direct"), text.index("#### B"))

    def test_sans_titres_le_projet_sert_de_chemin(self):
        text = assemble([part(15, [], "texte", project="Gamma")], "path")

        self.assertTrue(text.startswith("## Gamma\n\n"))

    def test_regroupement_inconnu_refuse(self):
        with self.assertRaises(ValueError):
            assemble([part(15, ["Alpha"], "x")], "autre")
