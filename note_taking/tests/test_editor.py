"""Éditeur de note : CodeMirror embarqué, <textarea> conservé, garde-fous (#89, #228)."""

import re
from pathlib import Path

from django.conf import settings
from django.test import TestCase
from django.urls import reverse

from core.codemirror import imported_specifiers, load_packages
from note_taking.models import Note

STATIC_DIR = Path(settings.BASE_DIR) / "note_taking" / "static" / "note_taking"


class NoteEditorPageTests(TestCase):
    def pages(self):
        note = Note.objects.create(date="2025-11-24", body="# P\nx")
        return {
            "nouvelle note": reverse("note_taking:new_note"),
            "édition": reverse("note_taking:edit_note", args=[note.pk]),
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
                    '<script type="module" src="/static/note_taking/editor.js">', html
                )

    def test_textarea_conserve_pour_l_envoi_du_formulaire(self):
        for page, url in self.pages().items():
            with self.subTest(page=page):
                html = self.client.get(url).content.decode()
                self.assertRegex(html, r'<textarea name="body" id="body"')

    def test_garde_fou_charge_en_script_classique(self):
        """Ctrl+S et l'avertissement ne dépendent pas du chargement de CodeMirror."""
        for page, url in self.pages().items():
            with self.subTest(page=page):
                html = self.client.get(url).content.decode()
                self.assertRegex(
                    html,
                    r'<script src="/static/note_taking/note_form\.js" defer>',
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

    def test_modules_de_l_editeur_dans_la_liste_embarquee(self):
        names = {p.name for p in load_packages()}

        self.assertLessEqual(imported_specifiers(self.read("editor.js")), names)

    def test_scripts_sans_adresse_externe(self):
        for name in ("editor.js", "note_form.js"):
            with self.subTest(name=name):
                self.assertIsNone(re.search(r"https?://", self.read(name)))

    def test_garde_fou_ctrl_s_et_avertissement(self):
        source = self.read("note_form.js")

        self.assertIn("beforeunload", source)
        self.assertIn('"s"', source)
        self.assertIn("requestSubmit", source)
