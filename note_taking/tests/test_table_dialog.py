"""Édition d'un tableau dans une fenêtre à part (#436) : le HTML de la page, et ce que le
JavaScript promet (il n'est pas exécuté par les tests)."""

import re
import unittest
from pathlib import Path

from django.conf import settings
from django.test import SimpleTestCase, TestCase
from django.urls import reverse

STATIC_DIR = Path(settings.BASE_DIR) / "note_taking" / "static" / "note_taking"


def read(name: str) -> str:
    return (STATIC_DIR / name).read_text(encoding="utf-8")


class TableDialogTemplateTests(TestCase):
    @unittest.expectedFailure
    def test_fenetre_dans_un_template(self):
        """Clonée par le script : sans JavaScript, la page n'a rien d'inerte."""
        html = self.client.get(reverse("note_taking:new_note")).content.decode()
        template = re.search(
            r'<template id="table-dialog-template">(.*?)</template>', html, re.S
        )
        assert template is not None
        dialog = template[1]

        self.assertIn("<dialog", dialog)
        self.assertIn('aria-labelledby="table-dialog-title"', dialog)
        for label in ("Formater", "Annuler", "Valider", "Abandonner"):
            with self.subTest(label=label):
                self.assertRegex(dialog, rf'<button type="button"[^>]*>.*{label}')
        # Hors du formulaire de la note : ses boutons ne l'enregistrent pas.
        self.assertLess(
            html.index("</form>", html.index("note-form")), template.start()
        )


class TableDialogScriptTests(SimpleTestCase):
    @unittest.expectedFailure
    def test_entree_du_menu_absente_de_la_fenetre(self):
        self.assertRegex(
            read("editor_menu.js"),
            r'submenu: \[\s*\{\s*label: "Éditer le tableau…",\s*when: Boolean\(editTable\)',
        )

    @unittest.expectedFailure
    def test_menu_dans_la_fenetre_modale(self):
        """Ajouté à la page, il serait sous la fenêtre, et inerte."""
        self.assertIn(
            'view.dom.closest("dialog") ?? document.body', read("editor_menu.js")
        )

    @unittest.expectedFailure
    def test_une_seule_modification_de_la_note(self):
        script = read("table_dialog.js")

        self.assertEqual(script.count("noteView.dispatch("), 1)
        self.assertIn('isolateHistory.of("full")', script)

    @unittest.expectedFailure
    def test_modifications_non_validees_protegees(self):
        script = read("table_dialog.js")

        self.assertIn('"beforeunload"', script)
        self.assertNotIn("confirm(", script)

    @unittest.expectedFailure
    def test_retour_a_la_ligne_dans_la_note_seulement(self):
        """Ce que les deux éditeurs partagent (`createEditor`) ne fait pas revenir à la ligne."""
        script = read("editor.js")
        start = script.index("const createEditor =")
        shared = script[start : script.index("const view = createEditor(")]

        for name in ("EditorView.lineWrapping", "hangingIndent", "listKeymap"):
            with self.subTest(name=name):
                self.assertNotIn(name, shared)
                self.assertIn(name, script[start + len(shared) :])
