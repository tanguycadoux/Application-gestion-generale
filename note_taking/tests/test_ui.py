"""Tests du tableau des notes et des feuilles de note_taking."""

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

    def test_tableaux_du_contenu_rendu_encadres(self):
        css = self.read("note_taking/style.css")

        self.assertIn(".rendered-content table", css)

    def test_etat_actif_par_attribut_data(self):
        js = self.read("note_taking/table.js")

        self.assertIn("dataset.active", js)
