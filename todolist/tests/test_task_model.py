"""Tests du modèle des tâches : sujet, avancement, projet obligatoire, sans héritage
forcé du parent (#163)."""

from datetime import date

from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse

from core.models import Project, Section
from note_taking.models import Note
from note_taking.services import process_note_parts
from todolist.forms import TodoForm
from todolist.models import Todo


class ProgressTests(TestCase):
    def setUp(self):
        self.project = Project.objects.create(name="P")

    def test_avancement_nul_par_defaut(self):
        todo = Todo.objects.create(title="T", project=self.project)

        self.assertEqual(todo.progress, 0)
        self.assertFalse(todo.completed)

    def test_terminee_a_cent_pour_cent(self):
        todo = Todo.objects.create(title="T", project=self.project, progress=100)

        self.assertTrue(todo.completed)

    def test_avancement_au_pourcent_pres(self):
        """76 % se saisit : le champ n'impose pas de pas de 5 %."""
        form = TodoForm(
            data={"title": "T", "project": self.project.pk, "priority": "medium"}
        )

        self.assertNotIn("step", form.fields["progress"].widget.attrs)

    def test_avancement_borne(self):
        for value in (-1, 101):
            with self.subTest(value=value), self.assertRaises(ValidationError):
                Todo(title="T", project=self.project, progress=value).full_clean()

    def test_case_de_la_liste(self):
        todo = Todo.objects.create(title="T", project=self.project, progress=40)
        url = reverse("todolist:todo_toggle", args=[todo.pk])

        self.client.post(url, {"completed": True}, content_type="application/json")
        todo.refresh_from_db()
        self.assertEqual(todo.progress, 100)

        self.client.post(url, {"completed": False}, content_type="application/json")
        todo.refresh_from_db()
        self.assertEqual(todo.progress, 40)


class SectionAndProjectTests(TestCase):
    def setUp(self):
        self.project = Project.objects.create(name="P")

    def test_sujet_facultatif(self):
        section = Section.objects.create(project=self.project, name="S")

        todo = Todo.objects.create(title="T", project=self.project, section=section)

        self.assertEqual(todo.section, section)
        self.assertIsNone(Todo.objects.create(title="U", project=self.project).section)

    def test_projet_obligatoire(self):
        form = TodoForm(data={"title": "T", "priority": "medium", "progress": 0})

        self.assertFalse(form.is_valid())
        self.assertIn("project", form.errors)

    def test_champs_du_formulaire(self):
        self.assertEqual(
            list(TodoForm().fields),
            [
                "title",
                "description",
                "progress",
                "priority",
                "due_date",
                "project",
                "section",
                "tags",
                "parent",
            ],
        )


class NoForcedInheritanceTests(TestCase):
    """Le parent propose son projet et son échéance, il ne les impose pas."""

    def setUp(self):
        self.project = Project.objects.create(name="P")
        self.other = Project.objects.create(name="Autre")
        self.parent = Todo.objects.create(
            title="Parent", project=self.project, due_date=date(2025, 12, 1)
        )

    def test_projet_different_du_parent_conserve(self):
        child = Todo.objects.create(title="E", project=self.other, parent=self.parent)

        child.refresh_from_db()
        self.assertEqual(child.project, self.other)

    def test_echeance_absente_conservee(self):
        child = Todo.objects.create(title="E", project=self.project, parent=self.parent)

        child.refresh_from_db()
        self.assertIsNone(child.due_date)

    def test_formulaire_d_une_sous_tache_propose_projet_et_echeance(self):
        html = self.client.get(
            reverse("todolist:todo_create") + f"?parent={self.parent.pk}"
        ).content.decode()

        self.assertRegex(html, rf'<option value="{self.project.pk}" selected>')
        self.assertIn('value="2025-12-01"', html)

    def test_boucle_toujours_refusee(self):
        child = Todo.objects.create(title="E", project=self.project, parent=self.parent)
        self.parent.parent = child

        with self.assertRaises(ValidationError):
            self.parent.save()


class TaskFromNoteTests(TestCase):
    def process(self, body: str) -> Todo:
        note = Note.objects.create(date="2025-11-24", body=body)
        process_note_parts(note)
        return Todo.objects.get()

    def test_sujet_de_la_note_part(self):
        todo = self.process(
            "# P\n## Réunion\n### TODO\n::: {.metadata}\ntags: [urgent]\n:::\n- Tâche"
        )

        self.assertEqual(todo.section.name, "Réunion")
        self.assertEqual(list(todo.tags.values_list("name", flat=True)), ["urgent"])

    def test_description_vide(self):
        todo = self.process("# P\n## S\n### TODO\n- Tâche")

        self.assertEqual(todo.description, "")

    def test_sans_sujet(self):
        todo = self.process("# P\n### TODO\n- Tâche")

        self.assertIsNone(todo.section)
