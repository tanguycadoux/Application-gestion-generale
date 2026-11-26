"""Une sélection n'emporte que le contenu, pas l'interface (#497).

Ctrl+A ou une sélection à la souris, collés ailleurs, ne doivent pas ramener les
libellés des boutons, le menu, le plan, le `Ctrl K` de la barre de recherche…
"""

from django.test import TestCase
from django.urls import reverse

from core.templatetags.ui import button

from .stylesheets import read_source_css


class SelectionRulesTests(TestCase):
    def setUp(self):
        self.css = read_source_css()

    def test_interface_non_selectionnable(self):
        self.assertIn(
            'nav, button, [role="button"], summary, kbd {\n        user-select: none;',
            self.css,
        )

    def test_texte_indicatif_des_champs_non_selectionnable(self):
        self.assertIn("::placeholder {\n        user-select: none;", self.css)

    def test_texte_tape_reste_selectionnable(self):
        self.assertIn(
            "input, textarea, [contenteditable] {\n        user-select: text;",
            self.css,
        )

    def test_composant_bouton_couvert_par_la_regle(self):
        # Le composant rend un `<button>` ou un `<a>` : le lien-bouton porte la classe.
        self.assertIn("select-none", button("Ouvrir", href="/x/")["classes"])


class SelectionTemplatesTests(TestCase):
    def test_en_tete_et_lien_d_evitement(self):
        html = self.client.get(reverse("core:index")).content.decode()

        self.assertRegex(html, r'<a href="#contenu" class="[^"]*\bselect-none\b')
        self.assertRegex(html, r'<header class="[^"]*\bselect-none\b')

    def test_compteur_des_resultats_de_recherche(self):
        from note_taking.models import Note
        from note_taking.services import process_passages

        note = Note.objects.create(date="2026-11-02", body="# P\nbanc thermique")
        process_passages(note)

        html = self.client.get(reverse("note_taking:notes_search"), {"q": "banc"})
        self.assertRegex(
            html.content.decode(), r'<p class="[^"]*\bselect-none\b[^"]*">1 passage'
        )
