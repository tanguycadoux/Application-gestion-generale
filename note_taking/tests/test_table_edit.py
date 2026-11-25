"""Lignes et colonnes d'un tableau dans l'éditeur (#435) : ce que le JavaScript promet (il
n'est pas exécuté par les tests)."""

import re
import unittest
from pathlib import Path

from django.conf import settings
from django.test import SimpleTestCase

STATIC_DIR = Path(settings.BASE_DIR) / "note_taking" / "static" / "note_taking"


class TableEditTests(SimpleTestCase):
    def read(self, name: str) -> str:
        return (STATIC_DIR / name).read_text(encoding="utf-8")

    @unittest.expectedFailure
    def test_entrees_du_sous_menu_tableau(self):
        script = self.read("table_edit.js")

        for label in (
            "Insérer une ligne avant",
            "Insérer une ligne après",
            "Insérer une colonne avant",
            "Insérer une colonne après",
            "Supprimer la ligne",
            "Supprimer la colonne",
            "Dimensions…",
        ):
            with self.subTest(label=label):
                self.assertIn(f'"{label}"', script)
        self.assertIn(
            "...tableEntries(view, pos, showForm)", self.read("editor_menu.js")
        )

    @unittest.expectedFailure
    def test_une_seule_modification_sans_confirmation(self):
        """Un Ctrl+Z annule la commande entière, et elle seule."""
        script = self.read("table_edit.js")

        self.assertEqual(script.count("view.dispatch("), 1)
        self.assertIn('isolateHistory.of("full")', script)
        self.assertNotIn("confirm(", script)

    @unittest.expectedFailure
    def test_commandes_independantes_du_menu(self):
        self.assertNotIn(
            "editor_menu.js", re.sub(r"//.*", "", self.read("table_edit.js"))
        )

    @unittest.expectedFailure
    def test_legende_collee_laissee_telle_quelle(self):
        """L'analyseur en fait une ligne du tableau ; « Formater » lui mettait des barres."""
        script = self.read("tables.js")
        find = script[script.index("export function findTables(") :]

        self.assertIn("lastRow(", find[: find.index("\n}\n")])
