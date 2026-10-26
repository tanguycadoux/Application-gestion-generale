"""Une seule règle d'urgence, et la case cochée sans rechargement (#189)."""

import json
import re
import unittest
from datetime import timedelta
from pathlib import Path

from django.conf import settings
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from core.models import Project
from todolist.models import Todo

TODAY = timezone.localdate()
SCRIPT = Path(settings.BASE_DIR) / "todolist" / "static" / "todolist" / "todo.js"


class DueSignalTests(TestCase):
    def setUp(self):
        self.project = Project.objects.create(name="P")

    def task(self, days: int | None, **fields) -> Todo:
        due = TODAY + timedelta(days=days) if days is not None else None
        return Todo(title="T", project=self.project, due_date=due, **fields)

    @unittest.expectedFailure
    def test_signal_porte_par_le_modele(self):
        for days, expected in (
            (-1, "overdue"),
            (0, "soon"),
            (3, "soon"),
            (4, "normal"),
            (None, "normal"),
        ):
            with self.subTest(days=days):
                self.assertEqual(self.task(days).due_signal, expected)
        self.assertEqual(self.task(-5, done=True).due_signal, "done")

    @unittest.expectedFailure
    def test_plus_de_seconde_regle(self):
        self.assertFalse(hasattr(Todo, "due_status"))


class LiveToggleTests(TestCase):
    def setUp(self):
        project = Project.objects.create(name="P")
        self.parent = Todo.objects.create(title="Parent", project=project)
        self.child = Todo.objects.create(
            title="Enfant", project=project, parent=self.parent
        )

    def toggle(self, todo: Todo, completed: bool):
        return self.client.post(
            reverse("todolist:todo_toggle", args=[todo.pk]),
            json.dumps({"completed": completed}),
            content_type="application/json",
        )

    @unittest.expectedFailure
    def test_lignes_modifiees_renvoyees_a_jour(self):
        rows = self.toggle(self.child, True).json()["rows"]

        self.assertEqual(set(rows), {str(self.child.pk), str(self.parent.pk)})
        child_row = rows[str(self.child.pk)]
        self.assertTrue(child_row.startswith(f'<tr data-task-id="{self.child.pk}"'))
        self.assertRegex(child_row, r'class="todo-toggle"[^>]* checked')
        # Le parent, dont l'avancement passe à 100 %, est à valider.
        self.assertIn('value="100"', rows[str(self.parent.pk)])

    @unittest.expectedFailure
    def test_liste_mise_a_jour_sur_place(self):
        html = self.client.get(reverse("todolist:todo_list")).content.decode()

        self.assertIn("data-live-rows", html)
        self.assertIn(f'<tr data-task-id="{self.child.pk}"', html)

    def test_detail_recharge_la_page(self):
        """L'en-tête et la frise du détail changent aussi : la page se recharge."""
        html = self.client.get(
            reverse("todolist:todo_detail", args=[self.parent.pk])
        ).content.decode()

        self.assertNotIn("data-live-rows", html)

    @unittest.expectedFailure
    def test_script_remplace_les_lignes_et_signale_un_echec(self):
        script = SCRIPT.read_text(encoding="utf-8")

        self.assertIn("data-live-rows", script)
        self.assertIn("outerHTML", script)
        # En cas d'échec, la case revient à son état et un toast le dit.
        self.assertIn("response.ok", script)
        self.assertRegex(script, r'Alert\.toast\([^)]*type: "error"')
        self.assertIsNone(re.search(r"^\s*location\.reload\(\);\s*$", script, re.M))
