"""Tâches sans échéance (#384) : le filtre de la liste, et l'absence d'échéance
déclarée voulue, qui sort la tâche du rappel de l'accueil."""

from datetime import date

from django.test import TestCase
from django.urls import reverse

from core.models import Project
from note_taking.models import Note
from todolist.forms import TaskForm
from todolist.models import Task

LIST = reverse("todolist:task_list")


class DeclaredNoDueDateTests(TestCase):
    def setUp(self):
        self.project = Project.objects.create(name="ASTERICS", color="teal")

    def test_une_date_annule_le_choix(self):
        task = Task.objects.create(title="T", project=self.project, no_due_date=True)

        task.due_date = date(2030, 1, 1)
        task.save()

        task.refresh_from_db()
        self.assertFalse(task.no_due_date)

    def test_case_du_formulaire(self):
        form = TaskForm(
            data={
                "title": "T",
                "progress": "0",
                "priority": "medium",
                "project": self.project.pk,
                "no_due_date": "on",
            }
        )

        self.assertTrue(form.is_valid(), form.errors)
        self.assertTrue(form.save().no_due_date)

    def test_fiche_le_dit(self):
        task = Task.objects.create(title="T", project=self.project, no_due_date=True)

        response = self.client.get(reverse("todolist:task_detail", args=[task.pk]))

        self.assertContains(response, "Aucune, c'est voulu")


class NoDueDateFilterTests(TestCase):
    def setUp(self):
        project = Project.objects.create(name="ASTERICS", color="teal")
        note = Note.objects.create(date="2026-11-02")
        Task.objects.create(title="À fixer", project=project)
        Task.objects.create(title="Voulue", project=project, no_due_date=True)
        Task.objects.create(title="Datée", project=project, due_date=date(2030, 1, 1))
        Task.objects.create(
            title="Au bilan",
            project=project,
            created_from_note=True,
            note_date=note.date,
            note_line_text="Au bilan",
            note_state=Task.NoteState.TO_REVIEW,
        )

    def shown(self, due):
        response = self.client.get(LIST, {"due": due})
        return {
            row.task.title
            for group in response.context["groups"]
            for row in group.rows
            if not row.muted
        }

    def test_sans_echeance_a_fixer(self):
        """Comme le bloc « À traiter » : ni voulue, ni à revoir dans le bilan."""
        self.assertEqual(self.shown("none"), {"À fixer"})

    def test_sans_echeance_voulue(self):
        self.assertEqual(self.shown("declared"), {"Voulue"})

    def test_avec_echeance(self):
        self.assertEqual(self.shown("set"), {"Datée"})

    def test_filtre_sur_la_colonne_echeance_et_dans_le_resume(self):
        response = self.client.get(LIST, {"due": "none"})

        self.assertContains(response, 'id="filters-due"')
        self.assertContains(response, "Échéance : Sans échéance, à fixer")
