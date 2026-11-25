"""Menu du clic droit de l'éditeur (#437) : ce que le JavaScript promet (il n'est pas
exécuté par les tests)."""

from pathlib import Path
from unittest import expectedFailure

from django.conf import settings
from django.test import SimpleTestCase

STATIC_DIR = Path(settings.BASE_DIR) / "note_taking" / "static" / "note_taking"


class EditorMenuTests(SimpleTestCase):
    def read(self, name: str) -> str:
        return (STATIC_DIR / name).read_text(encoding="utf-8")

    @expectedFailure
    def test_une_seule_liste_decrit_le_menu(self):
        script = self.read("editor_menu.js")

        self.assertEqual(script.count("function entries("), 1)
        entries = script[script.index("function entries(") :]
        for label in ("Couper", "Copier", "Coller", "Insérer", "Tableau"):
            with self.subTest(label=label):
                self.assertIn(f'label: "{label}"', entries)

    @expectedFailure
    def test_presse_papiers_refuse_dit_ctrl_v(self):
        self.assertIn("Utilisez Ctrl+V", self.read("editor_menu.js"))

    @expectedFailure
    def test_tableaux_cherches_dans_toute_la_note(self):
        """L'arbre de la partie visible en oublierait."""
        script = self.read("tables.js")
        find = script[script.index("export function findTables(") :]

        self.assertIn("ensureSyntaxTree(state, state.doc.length", find[:600])

    @expectedFailure
    def test_tableaux_formates_en_une_modification(self):
        """Un seul `dispatch` pour tous : un Ctrl+Z annule le tout."""
        script = self.read("tables.js")
        body = script[script.index("export function formatTables(") :]
        body = body[: body.index("\n}\n")]

        self.assertEqual(body.count("view.dispatch("), 1)
