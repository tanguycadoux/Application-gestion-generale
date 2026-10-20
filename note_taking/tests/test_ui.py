"""Tests du style des pages de note_taking en classes Tailwind (#79)."""

from django.contrib.staticfiles import finders
from django.test import TestCase
from django.urls import reverse

from note_taking.models import Note
from note_taking.services import process_note_parts


class NoteListTableTests(TestCase):
    def setUp(self):
        note = Note.objects.create(date="2025-11-24", body="# P\nx")
        process_note_parts(note)

    def get(self) -> str:
        return self.client.get(reverse("note_taking:notes_list")).content.decode()

    def test_tableau_en_classes_tailwind(self):
        html = self.get()

        self.assertNotIn("notes-list-table", html)
        self.assertIn("even:bg-[oklch(96%_0_0)]", html)
        self.assertIn("data-active:bg-[oklch(92%_0_0)]", html)

    def test_points_d_accroche_du_script_conserves(self):
        html = self.get()

        self.assertIn('class="table-column-head ', html)
        self.assertIn('class="table-column-head__options ', html)


class StylesheetsTests(TestCase):
    def read(self, name: str) -> str:
        path = finders.find(name)
        assert isinstance(path, str)
        with open(path, encoding="utf-8") as file:
            return file.read()

    def test_plus_de_regles_globales_de_tableau(self):
        css = self.read("core/style.css")

        self.assertNotIn("table {", css)
        self.assertNotIn(".table-column-head", css)

    def test_tableaux_du_contenu_rendu_encadres(self):
        css = self.read("note_taking/style.css")

        self.assertIn(".rendered-content table", css)
        self.assertNotIn(".notes-list-table", css)

    def test_etat_actif_par_attribut_data(self):
        js = self.read("note_taking/table.js")

        self.assertIn("dataset.active", js)
        self.assertNotIn("--active-popover", js)
