"""Tests du style des formulaires : champs communs, libellés à gauche en grille (#132)."""

from django import forms
from django.test import TestCase
from django.urls import reverse

from core.icons import icon_svg
from core.models import Project
from core.templatetags.ui import BUTTON_VARIANTS
from note_taking.models import Note
from todolist.forms import TodoForm
from todolist.models import Todo

from .stylesheets import read_source_css

FORM_GRID = "grid grid-cols-[max-content_1fr] items-baseline gap-x-3 gap-y-3"


class FieldBaseStyleTests(TestCase):
    def setUp(self):
        self.html = read_source_css()

    def test_style_de_base_des_champs(self):
        self.assertIn(
            "@apply max-w-full rounded-lg border border-slate-300 bg-white px-2 py-1;",
            self.html,
        )

    def test_champs_bornes_a_leur_cellule(self):
        """Un <select> prend la largeur de sa plus longue option : sans borne, une
        longue option élargit la grille au-delà de l'écran."""
        self.assertIn(
            "@apply max-w-full rounded-lg border border-slate-300 bg-white px-2 py-1;",
            self.html,
        )

    def test_focus_et_erreur_des_champs(self):
        self.assertIn("outline-blue-700", self.html)
        self.assertIn('[aria-invalid="true"]', self.html)
        self.assertIn(".errorlist", self.html)

    def test_cases_et_bouton_de_fichier(self):
        self.assertIn("@apply accent-blue-700;", self.html)
        self.assertIn("::file-selector-button", self.html)


class FormGridTemplateTests(TestCase):
    """`{{ form }}` rend chaque champ en deux cellules de grille : libellé, champ."""

    def test_libelle_puis_cellule_du_champ(self):
        html = str(TodoForm())

        self.assertNotIn("<p>", html)
        self.assertInHTML(
            '<label for="id_title">Titre :</label>', html.replace("\xa0", " ")
        )
        self.assertIn('<div class="min-w-0">', html)

    def test_erreurs_dans_la_cellule_du_champ(self):
        form = TodoForm(data={"title": ""})
        form.is_valid()

        row = str(form).split('<label for="id_title">')[1].split("<label")[0]
        cell = row.split('<div class="min-w-0">')[1]
        self.assertIn('aria-invalid="true"', cell)
        self.assertLess(cell.index("<input"), cell.index('class="errorlist"'))

    def test_cases_a_cocher_en_groupe_nomme(self):
        class ChoicesForm(forms.Form):
            tags = forms.MultipleChoiceField(
                choices=[("a", "A"), ("b", "B")],
                widget=forms.CheckboxSelectMultiple,
            )

        html = str(ChoicesForm())

        self.assertIn('<span id="id_tags_label">Tags&nbsp;:</span>', html)
        self.assertIn('role="group" aria-labelledby="id_tags_label"', html)


SAVE_BUTTON = (
    '<button type="submit" form="{form}" class="{classes}" aria-label="{label}">'
    + icon_svg("save").replace("{", "{{").replace("}", "}}")
    + "</button>"
)


def page_header(html: str) -> str:
    return html[html.index("<header") : html.index("</header>")]


class SaveInHeaderTests(TestCase):
    """Enregistrer : bouton ghost en haut à droite, comme la barre d'outils d'une note."""

    def assert_save_in_header(self, html: str, form_id: str, label: str):
        self.assertIn(f'<form id="{form_id}"', html)
        self.assertInHTML(
            SAVE_BUTTON.format(
                form=form_id, classes=BUTTON_VARIANTS["ghost"], label=label
            ),
            page_header(html),
        )
        self.assertNotIn("col-start-2", html)

    def test_nouvelle_note(self):
        html = self.client.get(reverse("note_taking:new_note")).content.decode()

        self.assert_save_in_header(html, "note-form", "Enregistrer la note")

    def test_modification_d_une_note(self):
        note = Note.objects.create(date="2025-11-24", body="# P\nx")

        html = self.client.get(
            reverse("note_taking:edit_note", args=[note.date])
        ).content.decode()

        self.assert_save_in_header(html, "note-form", "Enregistrer la note")

    def test_formulaire_de_todo(self):
        html = self.client.get(reverse("todolist:todo_create")).content.decode()

        self.assert_save_in_header(html, "todo-form", "Enregistrer la tâche")


class FormPagesTests(TestCase):
    def test_formulaire_de_todo_en_grille(self):
        html = self.client.get(reverse("todolist:todo_create")).content.decode()

        self.assertIn(f'<form id="todo-form" method="post" class="{FORM_GRID}">', html)

    def test_formulaire_de_note_en_colonne_de_la_hauteur_restante(self):
        """Pas de grille : un seul champ large, qui défile dans sa zone (#89)."""
        note = Note.objects.create(date="2025-11-24", body="# P\nx")

        html = self.client.get(
            reverse("note_taking:edit_note", args=[note.date])
        ).content.decode()

        self.assertNotIn(FORM_GRID, html)
        self.assertIn('class="flex min-h-0 flex-1 flex-col gap-3"', html)
        self.assertIn('class="min-h-48 w-full flex-1 resize-none font-mono"', html)
        self.assertIn('<div class="flex h-full flex-col">', html)

    def test_import_libelle_a_gauche(self):
        html = self.client.get(reverse("note_taking:notes_list")).content.decode()

        self.assertNotIn('<p class="flex flex-col">', html)
        self.assertIn('<p class="flex items-baseline gap-2">', html)

    def test_fichier_source_libelle_a_gauche(self):
        note = Note.objects.create(date="2025-11-24", body="# P\nx")

        html = self.client.get(
            reverse("note_taking:note_detail", args=[note.date])
        ).content.decode()

        self.assertIn('<p class="flex items-baseline gap-2">', html)

    def test_modification_d_une_todo_accessible(self):
        todo = Todo.objects.create(
            project=Project.objects.get_or_create(name="P")[0], title="T"
        )

        response = self.client.get(reverse("todolist:todo_edit", args=[todo.pk]))

        self.assertEqual(response.status_code, 200)
