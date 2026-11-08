"""Assemblage des résultats en un document Markdown (#356) : sans accès à la base."""

import unittest
from datetime import date

from django.test import SimpleTestCase, TestCase
from django.urls import reverse

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


def level_part(day, levels, content):
    """Une note part aux niveaux donnés, (identité, nom en base), du projet au plus
    profond (#369)."""
    from note_taking.search_document import Level

    iso = date(2026, 10, day).isoformat()
    return DocPart(
        date=date(2026, 10, day),
        date_label=f"{day} octobre 2026",
        note_url=f"/notes/{iso}/",
        part_url=f"/notes/{iso}/#ancre",
        levels=tuple(Level(key, name) for key, name in levels),
        content=content,
    )


NORD = (1, "Chantier Nord")
NORD_MINUSCULE = (2, "Chantier nord")
REUNION = (10, "Réunion")
REUNION_SANS_ACCENT = (11, "Reunion")
PREPARATION = (20, "Préparation")
PREPARATION_SANS_ACCENT = (21, "Preparation")


class ByLevelTests(SimpleTestCase):
    """Un groupe par niveau (#369) : son identité, pas l'écriture de son nom."""

    @unittest.expectedFailure
    def test_projets_de_meme_nom_sans_casse_jamais_entrelaces(self):
        text = assemble(
            [
                level_part(15, [NORD], "nord15"),
                level_part(12, [NORD_MINUSCULE], "minuscule12"),
                level_part(10, [NORD], "nord10"),
            ],
            "path",
        )

        self.assertEqual(text.count("## Chantier Nord\n"), 1)
        self.assertEqual(text.count("## Chantier nord\n"), 1)
        self.assertLess(text.index("nord10"), text.index("## Chantier nord"))
        self.assertLess(text.index("nord15"), text.index("nord10"))

    @unittest.expectedFailure
    def test_niveaux_de_meme_nom_sans_accents_jamais_entrelaces(self):
        text = assemble(
            [
                level_part(15, [NORD, REUNION, PREPARATION], "avec15"),
                level_part(
                    12, [NORD, REUNION_SANS_ACCENT, PREPARATION_SANS_ACCENT], "sans12"
                ),
                level_part(10, [NORD, REUNION, PREPARATION], "avec10"),
                level_part(5, [NORD, REUNION], "direct5"),
            ],
            "path",
        )

        self.assertEqual(
            text,
            "## Chantier Nord\n\n### Réunion\n\n"
            "**[5 octobre 2026](/notes/2026-10-05/#ancre)**\n\ndirect5\n\n"
            "#### Préparation\n\n"
            "**[15 octobre 2026](/notes/2026-10-15/#ancre)**\n\navec15\n\n"
            "**[10 octobre 2026](/notes/2026-10-10/#ancre)**\n\navec10\n\n"
            "### Reunion\n\n#### Preparation\n\n"
            "**[12 octobre 2026](/notes/2026-10-12/#ancre)**\n\nsans12\n",
        )

    @unittest.expectedFailure
    def test_par_date_un_meme_niveau_qui_suit_n_est_pas_rouvert(self):
        text = assemble(
            [
                level_part(15, [NORD_MINUSCULE, REUNION], "minuscule"),
                level_part(15, [NORD, REUNION, PREPARATION], "un"),
                level_part(15, [NORD, REUNION, PREPARATION], "deux"),
            ],
            "date",
        )

        self.assertEqual(
            text,
            "## [Note du 15 octobre 2026](/notes/2026-10-15/)\n\n"
            "### Chantier nord\n\n#### Réunion\n\nminuscule\n\n"
            "### Chantier Nord\n\n#### Réunion\n\n##### Préparation\n\n"
            "un\n\ndeux\n",
        )


class SearchFormKeepsViewTests(TestCase):
    url = reverse("note_taking:notes_search")

    def test_le_formulaire_garde_la_vue_document(self):
        response = self.client.get(
            self.url, {"q": "x", "view": "document", "group": "path"}
        )

        self.assertContains(
            response, '<input type="hidden" name="view" value="document">'
        )
        self.assertContains(response, '<input type="hidden" name="group" value="path">')

    def test_vue_extraits_sans_champ_cache(self):
        response = self.client.get(self.url, {"q": "x"})

        self.assertNotContains(response, 'name="view"')
