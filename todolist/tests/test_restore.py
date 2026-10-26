"""Tâches écartées : les revoir et les rétablir (#290).

Rétablir une tâche rétablit ses sous-tâches écartées, et le dit. Elle retrouve
son parent s'il est encore affiché, sinon elle revient à la racine, signalé. Pas
de suppression définitive : sa ligne reviendrait en tâche.
"""

import unittest

from django.contrib.messages import get_messages
from django.test import TestCase
from django.urls import reverse

from note_taking.models import Note
from note_taking.services import process_note_parts
from todolist.models import Todo
from todolist.services import remove_task

BODY = "# P\n### TODO\n- A\n  - B\n  - C\n- D"


class RestoreTestCase(TestCase):
    def setUp(self):
        self.note = Note.objects.create(date="2025-11-24", body=BODY)
        process_note_parts(self.note)
        Todo.objects.update(note_state=Todo.NoteState.REVIEWED)

    def task(self, title: str) -> Todo:
        return Todo.all_objects.get(title=title)

    def restore(self, title: str):
        return self.client.post(
            reverse("todolist:todo_restore", args=[self.task(title).pk])
        )

    def message(self, response) -> str:
        return " ".join(str(m) for m in get_messages(response.wsgi_request))


class DismissedListTests(RestoreTestCase):
    def test_section_des_ecartees(self):
        remove_task(self.task("A"))

        response = self.client.get(reverse("todolist:todo_list"))

        self.assertContains(response, "Écartées (1)")
        self.assertEqual(
            [row.task.title for row in response.context["dismissed_rows"]], ["A"]
        )

    def test_confirmation_annonce_les_sous_taches(self):
        remove_task(self.task("A"))

        response = self.client.get(reverse("todolist:todo_list"))

        self.assertContains(response, "Rétablir la tâche « A » et ses 2 sous-tâches ?")


class MixedTreeTests(RestoreTestCase):
    """Un arbre écarté avec des tâches saisies à la main se rétablit intact."""

    def setUp(self):
        super().setUp()
        self.manual = Todo.objects.create(
            title="M", project=self.task("A").project, parent=self.task("A")
        )

    @unittest.expectedFailure
    def test_tache_saisie_a_la_main_retablie_comme_telle(self):
        remove_task(self.task("A"))

        self.restore("A")

        manual = self.task("M")
        self.assertEqual((manual.note_state, manual.parent), ("", self.task("A")))
        self.assertEqual(self.task("B").note_state, Todo.NoteState.REVIEWED)

    @unittest.expectedFailure
    def test_racine_saisie_a_la_main_dans_les_ecartees(self):
        Todo.objects.filter(pk=self.manual.pk).update(parent=None)
        Todo.objects.filter(title="D").update(parent=self.manual)
        remove_task(self.task("M"))

        response = self.client.get(reverse("todolist:todo_list"))

        self.assertContains(response, "Saisie à la main")
        self.restore("M")
        self.assertEqual(self.task("D").note_state, Todo.NoteState.REVIEWED)


class RestoreTests(RestoreTestCase):
    def test_retablit_la_tache_et_ses_sous_taches(self):
        remove_task(self.task("A"))

        response = self.restore("A")

        self.assertRedirects(response, reverse("todolist:todo_list"))
        self.assertEqual(
            sorted(Todo.objects.values_list("title", flat=True)), ["A", "B", "C", "D"]
        )
        self.assertEqual(
            self.message(response),
            "La tâche « A » et ses 2 sous-tâches sont rétablies.",
        )

    def test_revue_si_sa_ligne_est_dans_la_note(self):
        remove_task(self.task("D"))

        self.restore("D")

        self.assertEqual(self.task("D").note_state, Todo.NoteState.REVIEWED)

    def test_gardee_sans_sa_ligne_sinon(self):
        remove_task(self.task("D"))
        self.note.body = "# P\n### TODO\n- A\n  - B\n  - C"
        self.note.save()
        process_note_parts(self.note)

        self.restore("D")

        self.assertEqual(self.task("D").note_state, Todo.NoteState.DETACHED)

    def test_retrouve_son_parent_affiche(self):
        remove_task(self.task("B"))

        response = self.restore("B")

        self.assertEqual(self.task("B").parent, self.task("A"))
        self.assertEqual(self.message(response), "La tâche « B » est rétablie.")

    def test_parent_ecarte_retablie_a_la_racine(self):
        remove_task(self.task("A"))

        response = self.restore("B")

        self.assertIsNone(self.task("B").parent)
        self.assertEqual(self.task("A").note_state, Todo.NoteState.DISMISSED)
        self.assertEqual(
            self.message(response),
            "La tâche « B » est rétablie. Sa tâche parente « A » est écartée : "
            "elle est rétablie sans tâche parente.",
        )

    def test_avancement_du_parent_a_jour(self):
        Todo.objects.filter(title="C").update(progress=100)
        b = self.task("B")
        b.save()
        remove_task(b)
        self.assertEqual(self.task("A").progress, 100)

        self.restore("B")

        self.assertEqual(self.task("A").progress, 50)

    def test_tache_non_ecartee_introuvable(self):
        response = self.restore("A")

        self.assertEqual(response.status_code, 404)

    def test_methode_get_refusee(self):
        remove_task(self.task("A"))

        response = self.client.get(
            reverse("todolist:todo_restore", args=[self.task("A").pk])
        )

        self.assertEqual(response.status_code, 405)
