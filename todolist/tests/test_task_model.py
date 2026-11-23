"""Tests du modèle des tâches : sujet, avancement, projet obligatoire, sans héritage
forcé du parent (#163)."""

from datetime import date

from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse

from core.models import Project, Section
from note_taking.models import Note
from note_taking.services import process_passages
from todolist.forms import TaskForm
from todolist.models import Task


class ProgressTests(TestCase):
    def setUp(self):
        self.project = Project.objects.create(name="P")

    def test_avancement_nul_par_defaut(self):
        task = Task.objects.create(title="T", project=self.project)

        self.assertEqual(task.progress, 0)
        self.assertFalse(task.completed)

    def test_terminee_a_cent_pour_cent(self):
        task = Task.objects.create(title="T", project=self.project, progress=100)

        self.assertTrue(task.completed)

    def test_avancement_au_pourcent_pres(self):
        """76 % se saisit : le champ n'impose pas de pas de 5 %."""
        form = TaskForm(
            data={"title": "T", "project": self.project.pk, "priority": "medium"}
        )

        self.assertNotIn("step", form.fields["progress"].widget.attrs)

    def test_avancement_borne(self):
        for value in (-1, 101):
            with self.subTest(value=value), self.assertRaises(ValidationError):
                Task(title="T", project=self.project, progress=value).full_clean()

    def test_case_de_la_liste(self):
        task = Task.objects.create(title="T", project=self.project, progress=40)
        url = reverse("todolist:task_toggle", args=[task.pk])

        self.client.post(url, {"completed": True}, content_type="application/json")
        task.refresh_from_db()
        self.assertEqual(task.progress, 100)

        self.client.post(url, {"completed": False}, content_type="application/json")
        task.refresh_from_db()
        self.assertEqual(task.progress, 40)


class SectionAndProjectTests(TestCase):
    def setUp(self):
        self.project = Project.objects.create(name="P")

    def test_sujet_facultatif(self):
        section = Section.objects.create(project=self.project, name="S")

        task = Task.objects.create(title="T", project=self.project, section=section)

        self.assertEqual(task.section, section)
        self.assertIsNone(Task.objects.create(title="U", project=self.project).section)

    def test_projet_facultatif(self):
        """#385 : une tâche peut être « à rattacher à un projet »."""
        form = TaskForm(data={"title": "T", "priority": "medium", "progress": 0})

        self.assertTrue(form.is_valid(), form.errors)
        self.assertIsNone(form.save().project)

    def test_chemin_sans_projet_refuse(self):
        form = TaskForm(
            data={
                "title": "T",
                "priority": "medium",
                "progress": 0,
                "section_path": "S",
            }
        )

        self.assertFalse(form.is_valid())
        self.assertIn("section_path", form.errors)

    def test_champs_du_formulaire(self):
        self.assertEqual(
            list(TaskForm().fields),
            [
                "title",
                "description",
                "progress",
                "priority",
                "due_date",
                "no_due_date",
                "project",
                "section_path",
                "tags",
                "parent",
            ],
        )


class NoForcedInheritanceTests(TestCase):
    """Le parent propose son projet et son échéance, il ne les impose pas."""

    def setUp(self):
        self.project = Project.objects.create(name="P")
        self.other = Project.objects.create(name="Autre")
        self.parent = Task.objects.create(
            title="Parent", project=self.project, due_date=date(2025, 12, 1)
        )

    def test_projet_different_du_parent_conserve(self):
        child = Task.objects.create(title="E", project=self.other, parent=self.parent)

        child.refresh_from_db()
        self.assertEqual(child.project, self.other)

    def test_echeance_absente_conservee(self):
        child = Task.objects.create(title="E", project=self.project, parent=self.parent)

        child.refresh_from_db()
        self.assertIsNone(child.due_date)

    def test_formulaire_d_une_sous_tache_propose_projet_et_echeance(self):
        html = self.client.get(
            reverse("todolist:task_create") + f"?parent={self.parent.pk}"
        ).content.decode()

        self.assertRegex(html, rf'<option value="{self.project.pk}" selected>')
        self.assertIn('value="2025-12-01"', html)

    def test_boucle_toujours_refusee(self):
        child = Task.objects.create(title="E", project=self.project, parent=self.parent)
        self.parent.parent = child

        with self.assertRaises(ValidationError):
            self.parent.save()


class TaskFromNoteTests(TestCase):
    def process(self, body: str) -> Task:
        note = Note.objects.create(date="2025-11-24", body=body)
        process_passages(note)
        return Task.objects.get()

    def test_description_vide(self):
        task = self.process("# P\n## S\n::: {.metadata}\ntodo: true\n:::\n- Tâche")

        self.assertEqual(task.description, "")

    def test_sans_chemin(self):
        task = self.process("# P\n::: {.metadata}\ntodo: true\n:::\n- Tâche")

        self.assertIsNone(task.section)
        self.assertEqual(list(task.tags.values_list("name", flat=True)), [])
