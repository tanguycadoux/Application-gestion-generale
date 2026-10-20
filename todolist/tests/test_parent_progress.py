"""Tests de la complétion d'un parent, calculée à partir de ses enfants (#164)."""

import json

from django.test import TestCase
from django.urls import reverse

from core.models import Project
from todolist.forms import TodoForm
from todolist.models import Todo


class ParentProgressTestCase(TestCase):
    def setUp(self):
        self.project = Project.objects.create(name="P")
        self.parent = self.task("Parent")
        self.child = self.task("Enfant", parent=self.parent)
        self.other = self.task("Autre enfant", parent=self.parent)
        self.grandchild = self.task("Petit-enfant", parent=self.child)

    def task(self, title: str, **fields) -> Todo:
        return Todo.objects.create(title=title, project=self.project, **fields)

    def progress(self, *todos: Todo) -> list[int]:
        return [Todo.objects.get(pk=todo.pk).progress for todo in todos]

    def toggle(self, todo: Todo, completed: bool):
        return self.client.post(
            reverse("todolist:todo_toggle", args=[todo.pk]),
            json.dumps({"completed": completed}),
            content_type="application/json",
        )


class ComputedProgressTests(ParentProgressTestCase):
    def test_moyenne_des_enfants_sur_tous_les_niveaux(self):
        self.grandchild.progress = 60
        self.grandchild.save()

        # Enfant = 60 (son seul enfant), Parent = moyenne(60, 0) = 30.
        self.assertEqual(self.progress(self.child, self.parent), [60, 30])

    def test_parent_termine_quand_tous_ses_enfants_le_sont(self):
        for todo in (self.grandchild, self.other):
            todo.progress = 100
            todo.save()

        self.assertEqual(self.progress(self.child, self.parent), [100, 100])
        self.assertTrue(Todo.objects.get(pk=self.parent.pk).completed)

    def test_avancement_saisi_d_un_parent_ignore(self):
        self.parent.progress = 100
        self.parent.save()

        self.assertEqual(self.progress(self.parent), [0])

    def test_ajout_d_un_enfant(self):
        self.other.progress = 100
        self.other.save()
        self.grandchild.progress = 100
        self.grandchild.save()

        self.task("Nouveau", parent=self.parent)

        # moyenne(100, 100, 0)
        self.assertEqual(self.progress(self.parent), [67])

    def test_suppression_d_un_enfant(self):
        self.other.progress = 100
        self.other.save()

        self.child.delete()

        self.assertEqual(self.progress(self.parent), [100])

    def test_changement_de_parent(self):
        self.other.progress = 100
        self.other.save()
        new_parent = self.task("Nouveau parent")

        self.other.parent = new_parent
        self.other.save()

        self.assertEqual(self.progress(self.parent, new_parent), [0, 100])

    def test_parent_sans_plus_d_enfant_garde_sa_valeur(self):
        lone = self.task("Seul")
        child = self.task("E", parent=lone, progress=100)

        child.delete()

        self.assertEqual(self.progress(lone), [100])


class ParentFormTests(ParentProgressTestCase):
    def test_avancement_d_un_parent_non_modifiable(self):
        form = TodoForm(instance=self.parent)

        self.assertTrue(form.fields["progress"].disabled)
        self.assertIn("sous-tâches", str(form.fields["progress"].help_text))

    def test_avancement_d_une_tache_sans_sous_tache_modifiable(self):
        self.assertFalse(TodoForm(instance=self.other).fields["progress"].disabled)


class ToggleTests(ParentProgressTestCase):
    def test_cocher_une_tache_met_a_jour_ses_ancetres_seulement(self):
        response = self.toggle(self.grandchild, completed=True)

        self.assertEqual(response.json()["status"], "ok")
        self.assertEqual(
            self.progress(self.grandchild, self.child, self.parent, self.other),
            [100, 100, 50, 0],
        )

    def test_basculer_un_parent_refuse(self):
        response = self.toggle(self.parent, completed=True)

        self.assertEqual(response.status_code, 400)
        self.assertEqual(self.progress(self.parent, self.child), [0, 0])

    def test_plus_de_confirmation_native(self):
        from django.contrib.staticfiles import finders

        path = finders.find("todolist/todo.js")
        assert isinstance(path, str)
        script = open(path, encoding="utf-8").read()

        self.assertNotIn("confirm(", script)
        self.assertNotIn("force", script)

    def test_case_d_un_parent_desactivee_avec_son_avancement(self):
        self.grandchild.progress = 100
        self.grandchild.save()

        html = self.client.get(reverse("todolist:todo_list")).content.decode()

        self.assertRegex(html, rf'data-id="{self.parent.pk}"[^>]*disabled')
        self.assertIn("50 %", html)
