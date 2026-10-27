"""Nombre de requêtes des listes, indépendant du nombre de lignes (#188)."""

from datetime import date

from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from core.models import Project
from note_taking.models import Note
from note_taking.services import process_note_parts
from todolist.models import Todo


class ListQueriesTests(TestCase):
    def queries(self, url: str) -> int:
        with CaptureQueriesContext(connection) as context:
            self.assertEqual(self.client.get(url).status_code, 200)
        return len(context.captured_queries)

    def add_tasks(self, count: int):
        a = Project.objects.get_or_create(name="A")[0]
        b = Project.objects.get_or_create(name="B")[0]
        for i in range(count):
            parent = Todo.objects.create(
                title=f"Parent {i}", project=a, due_date=date(2025, 11, 24)
            )
            # Sous-tâche incohérente : autre projet, échéance après le parent.
            Todo.objects.create(
                title=f"Enfant {i}",
                project=b,
                parent=parent,
                due_date=date(2025, 12, 1),
            )

    def add_notes(self, count: int):
        for _ in range(count):
            note = Note.objects.create(
                date=date(2025, 11, 1 + Note.objects.count()), body="# A\nx\n# B\ny"
            )
            process_note_parts(note)

    def test_liste_des_taches(self):
        url = reverse("todolist:todo_list")
        self.add_tasks(2)
        few = self.queries(url)
        self.add_tasks(6)

        self.assertEqual(self.queries(url), few)

    def test_detail_d_une_tache_parente(self):
        a = Project.objects.create(name="A")
        parent = Todo.objects.create(title="Parent", project=a)
        url = reverse("todolist:todo_detail", args=[parent.pk])
        Todo.objects.create(title="E0", project=a, parent=parent)
        few = self.queries(url)
        for i in range(1, 6):
            Todo.objects.create(title=f"E{i}", project=a, parent=parent)

        self.assertEqual(self.queries(url), few)

    def test_liste_des_notes(self):
        url = reverse("note_taking:notes_list")
        self.add_notes(2)
        few = self.queries(url)
        self.add_notes(6)

        self.assertEqual(self.queries(url), few)

    def test_projets_des_notes_par_nom(self):
        note = Note.objects.create(date="2025-11-24", body="# B\nx\n# A\ny\n# B\nz")
        process_note_parts(note)

        html = self.client.get(reverse("note_taking:notes_list")).content.decode()

        # Les lignes du tableau, pas le panneau de filtres, qui liste aussi les projets.
        rows = html[html.index("<tbody") :]

        self.assertLess(rows.index(">A<"), rows.index(">B<"))
        self.assertEqual(rows.count(">B<"), 1)
