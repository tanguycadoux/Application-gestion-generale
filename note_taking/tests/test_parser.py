"""Tests du parseur de notes qmd (`parse_note_raw_file_as_dict`).

Ces tests figent le comportement décrit dans le README : `#` donne le projet, les
titres `##` à `######` le chemin sous le projet (#287), et seuls les blocs
`{.metadata}` donnent des tags.

Le test `ExampleNoteTests` compare l'analyse complète de
`data/exemple.qmd` au résultat attendu `data/exemple.json`. Pour
régénérer ce fichier après un changement de comportement voulu :

    UPDATE_GOLDEN=1 python manage.py test note_taking.tests.test_parser

puis relire le diff de `exemple.json` avant de commiter.
"""

import json
import os
from pathlib import Path

from django.test import SimpleTestCase

from note_taking.exceptions import NoteParseError
from note_taking.qmd.parser import (
    ParsedNote,
    ParsedPart,
    parse_note,
    parse_note_raw_file_as_dict,
)

DATA_DIR = Path(__file__).parent / "data"


def parse(raw: str) -> dict:
    return parse_note_raw_file_as_dict("2025-11-24", raw)


def normalize(parsed: dict) -> dict:
    """Trie les tags, dont l'ordre dépend d'un set et n'est pas garanti."""
    return {
        **parsed,
        "content": [
            {**part, "tags": sorted(part["tags"])} for part in parsed["content"]
        ],
    }


def parts(raw: str) -> list[tuple]:
    """Résumé des note parts : (projet, chemin, tags triés, lignes)."""
    return [
        (part["project"], part["path"], sorted(part["tags"]), part["content"])
        for part in parse(raw)["content"]
    ]


class ParsedNoteTests(SimpleTestCase):
    def test_resultat_type(self):
        note = parse_note("2025-11-24", "---\ndate: 2025-11-24\n---\n# P\n## S\nx")

        self.assertEqual(
            note,
            ParsedNote(
                file_date="2025-11-24",
                metadata={"date": "2025-11-24"},
                parts=[
                    ParsedPart(
                        project="P",
                        path=["S"],
                        tags=[],
                        lines=["x"],
                        headings=["P", "S"],
                    )
                ],
            ),
        )

    def test_format_json_historique(self):
        note = parse_note("2025-11-24", "# P\n### A\nx")

        self.assertEqual(
            note.as_dict(),
            {
                "file date": "2025-11-24",
                "note metadata": {},
                "content": [
                    {"project": "P", "path": ["A"], "tags": [], "content": ["x"]}
                ],
            },
        )


class ExampleNoteTests(SimpleTestCase):
    def test_exemple_complet(self):
        raw = (DATA_DIR / "exemple.qmd").read_text(encoding="utf-8")
        result = normalize(parse(raw))
        expected_path = DATA_DIR / "exemple.json"

        if os.environ.get("UPDATE_GOLDEN"):
            expected_path.write_text(
                json.dumps(result, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )

        expected = json.loads(expected_path.read_text(encoding="utf-8"))
        self.assertEqual(result, expected)


class NoteMetadataTests(SimpleTestCase):
    def test_bloc_en_tete(self):
        result = parse("---\ndate: 2025-11-24\nauteur: moi\n---\n# P\nx")
        self.assertEqual(
            result["note metadata"], {"date": "2025-11-24", "auteur": "moi"}
        )

    def test_date_du_fichier_renvoyee(self):
        self.assertEqual(parse("# P\nx")["file date"], "2025-11-24")

    def test_sans_bloc(self):
        self.assertEqual(parse("# P\nx")["note metadata"], {})

    def test_metadonnee_mal_formee(self):
        with self.assertRaisesMessage(
            NoteParseError, "la forme attendue est « clé: valeur »"
        ):
            parse("---\npas de deux-points\n---\n# P\nx")


class HierarchyTests(SimpleTestCase):
    def test_projet_et_sujet(self):
        self.assertEqual(
            parts("# P\n## S\nx"),
            [("P", ["S"], [], ["x"])],
        )

    def test_texte_au_niveau_projet(self):
        self.assertEqual(parts("# P\nx"), [("P", [], [], ["x"])])

    def test_titres_2_a_6_forment_le_chemin(self):
        raw = "# P\n## S\n### T3\n#### T4\n##### T5\n###### T6\nx"
        self.assertEqual(
            parts(raw),
            [("P", ["S", "T3", "T4", "T5", "T6"], [], ["x"])],
        )

    def test_niveau_saute(self):
        """Un `###` sans `##` au-dessus est le premier niveau du chemin."""
        self.assertEqual(parts("# P\n### A\nx"), [("P", ["A"], [], ["x"])])

    def test_titre_moins_profond_retire_les_niveaux_plus_profonds(self):
        raw = "# P\n## S\n### A\n#### B\nx\n### C\ny"
        self.assertEqual(
            parts(raw),
            [
                ("P", ["S", "A", "B"], [], ["x"]),
                ("P", ["S", "C"], [], ["y"]),
            ],
        )

    def test_nouveau_sujet_retire_les_titres(self):
        raw = "# P\n## S1\n### A\nx\n## S2\ny"
        self.assertEqual(
            parts(raw),
            [("P", ["S1", "A"], [], ["x"]), ("P", ["S2"], [], ["y"])],
        )

    def test_nouveau_projet_retire_le_chemin(self):
        raw = "# P1\n## S\n### A\nx\n# P2\ny"
        self.assertEqual(
            parts(raw),
            [("P1", ["S", "A"], [], ["x"]), ("P2", [], [], ["y"])],
        )

    def test_titre_avec_virgule_reste_un_seul_niveau(self):
        self.assertEqual(
            parts("# P\n### Conception, fabrication\nx"),
            [("P", ["Conception, fabrication"], [], ["x"])],
        )

    def test_titre_avec_barre_reste_un_seul_niveau(self):
        self.assertEqual(
            parts("# P\n## Rapport RT17/A\nx"),
            [("P", ["Rapport RT17/A"], [], ["x"])],
        )

    def test_diese_sans_espace_n_est_pas_un_titre(self):
        self.assertEqual(parts("# P\n#hashtag"), [("P", [], [], ["#hashtag"])])


class TodoMarkerTests(SimpleTestCase):
    """`TODO` marque une section de tâches sans entrer dans le chemin (#297 le
    remplacera par les cases à cocher)."""

    def test_titre_todo_hors_du_chemin_et_tag(self):
        self.assertEqual(
            parts("# P\n## S\n### TODO\n- a"),
            [("P", ["S"], ["TODO"], ["- a"])],
        )

    def test_todo_a_n_importe_quelle_profondeur(self):
        self.assertEqual(
            parts("# P\n## S\n### Notes\n#### TODO\n- a"),
            [("P", ["S", "Notes"], ["TODO"], ["- a"])],
        )

    def test_niveaux_sous_le_titre_todo_gardes(self):
        self.assertEqual(
            parts("# P\n### TODO\n#### Détail\n- a"),
            [("P", ["Détail"], ["TODO"], ["- a"])],
        )

    def test_titre_todo_garde_dans_les_titres_de_la_section(self):
        """L'identité des tâches (#240) repose sur les titres tels qu'écrits."""
        note = parse_note("2025-11-24", "# P\n## S\n### TODO\n- a")

        self.assertEqual(note.parts[0].headings, ["P", "S", "TODO"])

    def test_todo_au_niveau_du_sujet_est_un_niveau_comme_un_autre(self):
        self.assertEqual(parts("# P\n## TODO\nx"), [("P", ["TODO"], [], ["x"])])

    def test_titre_todo_ne_vaut_que_tel_quel(self):
        self.assertEqual(parts("# P\n### Todo\nx"), [("P", ["Todo"], [], ["x"])])


class LocalMetadataTests(SimpleTestCase):
    def test_tags_ajoutes(self):
        raw = "# P\n### A\n::: {.metadata}\ntags: [m1, m2]\n:::\nx"
        self.assertEqual(parts(raw), [("P", ["A"], ["m1", "m2"], ["x"])])

    def test_meme_niveau_remplace(self):
        raw = (
            "# P\n### A\n"
            "::: {.metadata}\ntags: [m1]\n:::\nx\n"
            "::: {.metadata}\ntags: [m2]\n:::\ny"
        )
        self.assertEqual(
            parts(raw),
            [("P", ["A"], ["m1"], ["x"]), ("P", ["A"], ["m2"], ["y"])],
        )

    def test_herites_en_profondeur(self):
        raw = "# P\n### A\n::: {.metadata}\ntags: [m1]\n:::\n#### B\nx"
        self.assertEqual(parts(raw), [("P", ["A", "B"], ["m1"], ["x"])])

    def test_niveau_projet_et_sujet(self):
        raw = (
            "# P\n::: {.metadata}\ntags: [p]\n:::\n"
            "## S\n::: {.metadata}\ntags: [s]\n:::\nx"
        )
        self.assertEqual(parts(raw), [("P", ["S"], ["p", "s"], ["x"])])

    def test_nouveau_projet_retire_les_tags_du_projet(self):
        raw = "# P1\n::: {.metadata}\ntags: [p]\n:::\nx\n# P2\ny"
        self.assertEqual(
            parts(raw),
            [("P1", [], ["p"], ["x"]), ("P2", [], [], ["y"])],
        )

    def test_tags_non_tableau(self):
        with self.assertRaisesMessage(NoteParseError, "entre crochets"):
            parse("# P\n::: {.metadata}\ntags: a, b\n:::\nx")

    def test_tags_vides_ignores(self):
        """#20 : `tags: []` ou une virgule en trop produisaient un tag vide."""
        raw = "# P\n### A\n::: {.metadata}\ntags: [m1, , ]\n:::\nx"
        self.assertEqual(parts(raw), [("P", ["A"], ["m1"], ["x"])])

    def test_titre_suivant_meme_niveau_n_herite_pas(self):
        raw = "# P\n## S\n### A\n::: {.metadata}\ntags: [m1]\n:::\nx\n### B\ny"
        self.assertEqual(
            parts(raw),
            [("P", ["S", "A"], ["m1"], ["x"]), ("P", ["S", "B"], [], ["y"])],
        )

    def test_sujet_suivant_n_herite_pas(self):
        raw = "# P\n## S1\n::: {.metadata}\ntags: [m1]\n:::\nx\n## S2\ny"
        self.assertEqual(
            parts(raw),
            [("P", ["S1"], ["m1"], ["x"]), ("P", ["S2"], [], ["y"])],
        )

    def test_un_tag_du_bloc_n_est_jamais_un_niveau(self):
        """Le tag est une portée sur la branche ; un niveau s'écrit en titre (#287)."""
        as_tag = "# P\n## S\n::: {.metadata}\ntags: [tag]\n:::\n### S-S\nx"
        as_title = "# P\n## S\n### tag\n#### S-S\nx"

        self.assertEqual(parts(as_tag), [("P", ["S", "S-S"], ["tag"], ["x"])])
        self.assertEqual(parts(as_title), [("P", ["S", "tag", "S-S"], [], ["x"])])


class IgnoredBlocksTests(SimpleTestCase):
    def test_bloc_de_code_conserve_tel_quel(self):
        raw = "# P\n```\n# pas un titre\n::: {.metadata}\n```\nx"
        self.assertEqual(
            parts(raw),
            [("P", [], [], ["```", "# pas un titre", "::: {.metadata}", "```", "x"])],
        )

    def test_callout_titres_non_interpretes(self):
        raw = '# P\n::: {.callout-note title="t"}\n## pas un titre\nc\n:::\nx'
        [(project, path, tags, content)] = parts(raw)
        self.assertEqual((project, path, tags), ("P", [], []))
        self.assertIn("## pas un titre", content)

    def test_callout_conserve_dans_le_contenu(self):
        raw = '# P\n::: {.callout-note title="t"}\n## pas un titre\nc\n:::\nx'
        self.assertEqual(
            parts(raw),
            [
                (
                    "P",
                    [],
                    [],
                    [
                        '::: {.callout-note title="t"}',
                        "## pas un titre",
                        "c",
                        ":::",
                        "x",
                    ],
                )
            ],
        )


class FixedBugsTests(SimpleTestCase):
    """Non-régression des bugs corrigés du parseur (#34 à #38)."""

    def test_indentation_conservee(self):
        self.assertEqual(
            parts("# P\n- a\n    - b"),
            [("P", [], [], ["- a", "    - b"])],
        )

    def test_ligne_horizontale_conservee(self):
        raw = "---\ndate: 2025-11-24\n---\n# P\navant\n---\napres"
        self.assertEqual(parts(raw), [("P", [], [], ["avant", "---", "apres"])])

    def test_texte_avant_premier_projet_ignore(self):
        self.assertEqual(parts("intro\n# P\nx"), [("P", [], [], ["x"])])

    def test_metadonnee_contenant_deux_points(self):
        result = parse("---\nheure: 10:30\n---\n# P\nx")
        self.assertEqual(result["note metadata"], {"heure": "10:30"})

    def test_ligne_vide_avant_bloc_en_tete(self):
        result = parse("\n---\ndate: 2025-11-24\n---\n# P\nx")
        self.assertEqual(result["note metadata"], {"date": "2025-11-24"})
        self.assertEqual(
            parts("\n---\ndate: 2025-11-24\n---\n# P\nx"), [("P", [], [], ["x"])]
        )


class GroupingTests(SimpleTestCase):
    def test_regroupement_de_sections_non_adjacentes(self):
        raw = "# P\n### A\nx\n### B\ny\n### A\nz"
        self.assertEqual(
            parts(raw),
            [("P", ["A"], [], ["x", "z"]), ("P", ["B"], [], ["y"])],
        )

    def test_lignes_vides_en_bordure_retirees(self):
        self.assertEqual(
            parts("# P\n\n\nx\n\ny\n\n"),
            [("P", [], [], ["x", "", "y"])],
        )

    def test_part_vide_supprimee(self):
        self.assertEqual(
            parts("# P\n### Vide\n\n\n### A\nx"),
            [("P", ["A"], [], ["x"])],
        )

    def test_note_sans_contenu(self):
        self.assertEqual(parse("---\ndate: 2025-11-24\n---\n")["content"], [])
