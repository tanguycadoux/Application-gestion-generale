"""Conversion des sections TODO en cases à cocher (#297), sur du texte seul."""

from django.test import SimpleTestCase

from note_taking.qmd.todo_sections import convert_todo_sections


def convert(body: str) -> str:
    result = convert_todo_sections(body)
    assert not result.problems, result.problems
    return result.body


class ConversionTests(SimpleTestCase):
    def test_section_simple(self):
        self.assertEqual(
            convert("# P\n## S\n### TODO\n\n- A\n- B\n\n### Suite\ntexte"),
            "# P\n## S\n- [ ] A\n- [ ] B\n\n### Suite\ntexte",
        )

    def test_titre_retire_et_ligne_vide_qui_le_suit(self):
        self.assertEqual(convert("# P\n\n### TODO\n\n- A"), "# P\n\n- [ ] A")

    def test_ligne_vide_retiree_apres_un_titre(self):
        self.assertEqual(convert("# P\n### TODO\n\n- A"), "# P\n- [ ] A")

    def test_ligne_vide_gardee_apres_un_paragraphe(self):
        """Pandoc veut une ligne vide entre un paragraphe et une liste."""
        self.assertEqual(convert("texte\n### TODO\n\n- A"), "texte\n\n- [ ] A")

    def test_sous_listes_et_numerotees(self):
        self.assertEqual(
            convert("# P\n### TODO\n- A\n  - B\n1. C\n   * D"),
            "# P\n- [ ] A\n  - [ ] B\n1. [ ] C\n   * [ ] D",
        )

    def test_case_vide_deja_presente_gardee(self):
        self.assertEqual(
            convert("# P\n### TODO\n- [ ] A\n- B"), "# P\n- [ ] A\n- [ ] B"
        )

    def test_marqueur_seul_laisse(self):
        self.assertEqual(convert("# P\n### TODO\n-\n- A"), "# P\n-\n- [ ] A")

    def test_fins_de_ligne_windows_conservees(self):
        self.assertEqual(
            convert("# P\r\n### TODO\r\n\r\n- A\r\n- B\r\n"),
            "# P\r\n- [ ] A\r\n- [ ] B\r\n",
        )

    def test_toutes_profondeurs_de_deux_a_six(self):
        """Le niveau 2, un simple « sujet » avant #297, est converti lui aussi (#322)."""
        for hashes in ("##", "###", "####", "#####", "######"):
            with self.subTest(hashes=hashes):
                self.assertEqual(convert(f"# P\n{hashes} TODO\n- A"), "# P\n- [ ] A")

    def test_titre_de_niveau_deux_sous_le_projet(self):
        self.assertEqual(
            convert("# P\n## TODO\n\n- A\n- B\n\n# Q\ntexte"),
            "# P\n- [ ] A\n- [ ] B\n\n# Q\ntexte",
        )

    def test_projet_nomme_todo_non_converti(self):
        body = "# TODO\n- A\n"

        self.assertEqual(convert_todo_sections(body).sections, 0)

    def test_section_arretee_par_un_titre_de_meme_niveau(self):
        self.assertEqual(
            convert("# P\n### TODO\n- A\n### Notes\n- pas une tâche"),
            "# P\n- [ ] A\n### Notes\n- pas une tâche",
        )

    def test_section_arretee_par_un_titre_moins_profond(self):
        self.assertEqual(
            convert("# P\n## S\n### TODO\n- A\n## T\n- pas une tâche"),
            "# P\n## S\n- [ ] A\n## T\n- pas une tâche",
        )

    def test_titre_plus_profond_garde_et_sa_liste_convertie(self):
        self.assertEqual(
            convert("# P\n### TODO\n- A\n#### Détail\n- B"),
            "# P\n- [ ] A\n#### Détail\n- [ ] B",
        )

    def test_plusieurs_sections(self):
        result = convert_todo_sections("# P\n### TODO\n- A\n## S\n### TODO\n- B")

        self.assertEqual(result.sections, 2)
        self.assertEqual(result.body, "# P\n- [ ] A\n## S\n- [ ] B")

    def test_note_sans_section_inchangee(self):
        body = "# P\n## Todo\n- A\n### TODOS\n- B\n"
        result = convert_todo_sections(body)

        self.assertEqual((result.body, result.sections, result.changes), (body, 0, []))

    def test_titre_todo_dans_un_bloc_de_code_ou_un_callout_ignore(self):
        body = (
            "# P\n```\n### TODO\n- A\n```\n"
            '::: {.callout-note title="t"}\n### TODO\n- B\n:::\n'
        )

        self.assertEqual(convert_todo_sections(body).sections, 0)


class ChangesTests(SimpleTestCase):
    def test_lignes_modifiees_et_retirees(self):
        result = convert_todo_sections("# P\n### TODO\n\n- A")

        self.assertEqual(
            [(c.number, c.before, c.after) for c in result.changes],
            [(4, "- A", "- [ ] A"), (2, "### TODO", None), (3, "", None)],
        )

    def test_numeros_de_ligne_d_origine(self):
        result = convert_todo_sections("a\nb\n# P\n### TODO\n- A")

        self.assertEqual(
            sorted((c.number, c.after) for c in result.changes if c.after),
            [(5, "- [ ] A")],
        )


class ProblemsTests(SimpleTestCase):
    """Ce qui ne se convertit pas seul : la note est laissée telle quelle."""

    def problems(self, body: str) -> list[str]:
        result = convert_todo_sections(body)
        self.assertEqual(result.body, body)
        self.assertEqual(result.changes, [])
        return result.problems

    def test_case_cochee(self):
        self.assertEqual(
            len(self.problems("# P\n### TODO\n- [x] A")),
            1,
        )

    def test_paragraphe(self):
        [problem] = self.problems("# P\n### TODO\nUn paragraphe.\n- A")

        self.assertIn("Ligne 3", problem)
        self.assertIn("n'est pas un élément de liste", problem)

    def test_bloc_de_metadonnees(self):
        [problem] = self.problems("# P\n### TODO\n::: {.metadata}\ntags: [x]\n:::\n- A")

        self.assertIn("Ligne 3", problem)

    def test_code(self):
        self.assertTrue(self.problems("# P\n### TODO\n```\ncode\n```\n- A"))

    def test_titre_todo_imbrique(self):
        self.assertTrue(self.problems("# P\n### TODO\n- A\n#### TODO\n- B"))


class BoxesOutsideTests(SimpleTestCase):
    def test_cases_hors_des_sections_todo(self):
        body = (
            "# P\n- [ ] Ouverte\n- [x] Cochée\n### TODO\n- A\n## S\n  - [ ] Imbriquée"
        )

        result = convert_todo_sections(body)

        self.assertEqual(
            [(box.number, box.text) for box in result.open_boxes],
            [(2, "[ ] Ouverte"), (7, "[ ] Imbriquée")],
        )
        self.assertEqual(
            [(box.number, box.text) for box in result.done_boxes], [(3, "[x] Cochée")]
        )

    def test_cases_d_un_bloc_de_code_ignorees(self):
        result = convert_todo_sections("# P\n```\n- [ ] exemple\n```\n")

        self.assertEqual(result.open_boxes, [])


class ChunksTests(SimpleTestCase):
    """Les titres d'avant et d'après, pour ranger les tâches déjà créées (#240)."""

    def chunks(self, body: str) -> list[tuple[list[str], list[str]]]:
        return [
            (chunk.old_headings, chunk.new_headings)
            for chunk in convert_todo_sections(body).chunks
        ]

    def test_sans_titre_frere_le_chemin_ne_change_pas(self):
        self.assertEqual(
            self.chunks("# P\n## S\n### TODO\n- A"),
            [(["P", "S"], ["P", "S"])],
        )

    def test_le_titre_todo_remplacait_son_frere(self):
        """Retiré, il laisse la liste sous le titre qui le précédait."""
        self.assertEqual(
            self.chunks("# P\n## S\n### Notes\ntexte\n### TODO\n- A"),
            [(["P", "S"], ["P", "S", "Notes"])],
        )

    def test_titre_frere_plus_profond_aussi(self):
        self.assertEqual(
            self.chunks("# P\n## S\n### Notes\n#### Détail\n### TODO\n- A"),
            [(["P", "S"], ["P", "S", "Notes", "Détail"])],
        )

    def test_titre_plus_profond_dans_la_section(self):
        self.assertEqual(
            self.chunks("# P\n### Notes\n### TODO\n- A\n#### Détail\n- B"),
            [
                (["P"], ["P", "Notes"]),
                (["P", "Détail"], ["P", "Notes", "Détail"]),
            ],
        )

    def test_deuxieme_section_voit_la_note_deja_convertie(self):
        body = "# P\n## S\n### A\n### TODO\n- x\n## T\n### B\n### TODO\n- y"
        self.assertEqual(
            self.chunks(body),
            [(["P", "S"], ["P", "S", "A"]), (["P", "T"], ["P", "T", "B"])],
        )

    def test_lignes_avant_et_apres(self):
        [chunk] = convert_todo_sections("# P\n### TODO\n- A\n  - B").chunks

        self.assertEqual(chunk.before, ["- A", "  - B"])
        self.assertEqual(chunk.after, ["- [ ] A", "  - [ ] B"])
