"""Éditeur de note : CodeMirror embarqué, <textarea> conservé, garde-fous (#89, #228)."""

import re
import unittest
from pathlib import Path

from django.conf import settings
from django.templatetags.static import static
from django.test import TestCase
from django.urls import reverse

from core.codemirror import imported_specifiers, load_packages
from note_taking.models import Note
from note_taking.qmd.lists import CODE_INDENT

STATIC_DIR = Path(settings.BASE_DIR) / "note_taking" / "static" / "note_taking"


class NoteEditorPageTests(TestCase):
    def pages(self):
        note = Note.objects.create(date="2025-11-24", body="# P\nx")
        return {
            "nouvelle note": reverse("note_taking:new_note"),
            "édition": reverse("note_taking:edit_note", args=[note.date]),
        }

    def test_import_map_avant_le_module(self):
        for page, url in self.pages().items():
            with self.subTest(page=page):
                html = self.client.get(url).content.decode()
                self.assertEqual(html.count('<script type="importmap">'), 1)
                self.assertLess(
                    html.index('<script type="importmap">'),
                    html.index('<script type="module"'),
                )
                self.assertIn(
                    f'<script type="module" src="{static("note_taking/editor.js")}">',
                    html,
                )

    def test_garde_fou_charge_en_script_classique(self):
        """Ctrl+S et l'avertissement ne dépendent pas du chargement de CodeMirror."""
        for page, url in self.pages().items():
            with self.subTest(page=page):
                html = self.client.get(url).content.decode()
                self.assertIn(
                    f'<script src="{static("note_taking/note_form.js")}" defer>',
                    html,
                )

    def test_bouton_du_plan_dans_un_template(self):
        """Le bouton n'existe que si editor.js le clone : rien d'inerte sans JavaScript."""
        for page, url in self.pages().items():
            with self.subTest(page=page):
                html = self.client.get(url).content.decode()
                template = re.search(
                    r'<template id="outline-toggle">(?P<button>.*?)</template>',
                    html,
                    re.DOTALL,
                )
                assert template is not None
                self.assertIn('type="button"', template.group("button"))
                # Un texte visible, pas une icône seule.
                self.assertIn("Plan</button>", template.group("button"))
                self.assertNotIn("aria-label", template.group("button"))
                self.assertIn("data-editor-toolbar", html)

    def test_aide_rappelle_le_menu_du_clic_droit(self):
        """Le clic droit ouvre le menu d'insertion ; Maj + clic droit, celui du
        navigateur (#400)."""
        html = self.client.get(reverse("note_taking:new_note")).content.decode()
        match = re.search(r'<p id="editor-help"[^>]*>(.*?)</p>', html, re.S)
        help_line = match.group(1)

        self.assertIn("Clic droit ou Maj+F10", help_line)
        self.assertIn("Maj + clic droit : menu du navigateur", help_line)

    def test_tableaux_et_menu_branches_dans_l_editeur(self):
        """#400, #401, #402 : l'analyseur reconnaît les tableaux à barres."""
        source = (STATIC_DIR / "editor.js").read_text()

        self.assertIn("parser.configure([TaskList, Strikethrough, Table])", source)
        for name in ("tableLines", "editorMenu(", "pandocListMarks"):
            self.assertIn(name, source)

    def test_aide_de_l_editeur_cachee_sans_javascript(self):
        for page, url in self.pages().items():
            with self.subTest(page=page):
                html = self.client.get(url).content.decode()
                self.assertRegex(html, r'<p id="editor-help" hidden [^>]*>Ctrl\+Espace')

    def test_adresses_des_listes_de_suggestions_sur_le_formulaire(self):
        for page, url in self.pages().items():
            with self.subTest(page=page):
                html = self.client.get(url).content.decode()
                self.assertIn(
                    f'data-projects-url="{reverse("core:project_suggestions")}"', html
                )
                self.assertIn(
                    f'data-sections-url="{reverse("core:section_suggestions")}"', html
                )
                self.assertIn(
                    f'data-images-url="{reverse("note_taking:image_suggestions")}"',
                    html,
                )

    def test_pas_de_script_sur_les_autres_pages(self):
        html = self.client.get(reverse("note_taking:notes_list")).content.decode()

        self.assertNotIn("importmap", html)
        self.assertNotIn("editor.js", html)

    def test_formulaire_en_erreur_marque_tout_a_enregistrer(self):
        Note.objects.create(date="2025-11-24", body="x")

        response = self.client.post(
            reverse("note_taking:new_note"), {"date": "2025-11-24", "body": "y"}
        )

        self.assertContains(response, "data-unsaved")

    def test_formulaire_sans_erreur_sans_marque(self):
        html = self.client.get(reverse("note_taking:new_note")).content.decode()

        self.assertNotIn("data-unsaved", html)


class NoteEditorScriptsTests(TestCase):
    """Ce que le JavaScript promet (il n'est pas exécuté par les tests)."""

    def read(self, name: str) -> str:
        return (STATIC_DIR / name).read_text(encoding="utf-8")

    def test_modules_des_scripts_dans_la_liste_embarquee(self):
        names = {p.name for p in load_packages()}

        for script in (
            "editor.js",
            "outline.js",
            "suggestions.js",
            "capture.js",
            "images_capture.js",
            "lists.js",
        ):
            # Les imports relatifs sont nos propres fichiers.
            modules = {
                name
                for name in imported_specifiers(self.read(script))
                if not name.startswith(".")
            }
            with self.subTest(script=script):
                self.assertLessEqual(modules, names)

    def test_scripts_sans_adresse_externe(self):
        for name in (
            "editor.js",
            "note_form.js",
            "outline.js",
            "suggestions.js",
            "capture.js",
            "images_capture.js",
            "lists.js",
        ):
            with self.subTest(name=name):
                self.assertIsNone(re.search(r"https?://", self.read(name)))

    @unittest.expectedFailure
    def test_imbrication_des_listes_d_apres_la_regle_de_pandoc(self):
        """Sous `A.  `, l'arbre de l'analyseur se trompe de niveau (#417) : la coloration,
        Entrée et Tab suivent les éléments ouverts, comme `PandocListsPreprocessor`."""
        script = self.read("lists.js")

        match = re.search(r"^const CODE_INDENT = (\d+);", script, re.M)
        assert match is not None
        self.assertEqual(int(match.group(1)), CODE_INDENT)
        marks = script[script.index("function pandocMarks(") :]
        self.assertNotIn("knownToParser", marks)
