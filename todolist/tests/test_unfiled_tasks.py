"""Tâches « à ranger » (#385) : les cases du texte sans projet d'une note.

Le texte avant le premier `#` est un passage sans projet ; ses cases deviennent des
tâches sans projet ni chemin, à revoir dans le bilan de la note, où l'on choisit
leur projet. Tant qu'aucun projet n'est choisi, la tâche reste à revoir.
"""

from django.test import TestCase
from django.urls import reverse

from core.models import Project
from note_taking.models import Note
from note_taking.services import process_passages
from todolist.models import Task

BODY = "- [ ] appeler Paul\n\n# P\n- [ ] rangée"


class UnfiledTaskTests(TestCase):
    def setUp(self):
        self.note = Note.objects.create(date="2026-11-22", body=BODY)
        process_passages(self.note)
        self.unfiled = Task.objects.get(title="appeler Paul")

    def review(self, project: Project | None):
        filed = Task.objects.get(title="rangée")
        data: dict[str, object] = {
            "new-TOTAL_FORMS": "2",
            "new-INITIAL_FORMS": "2",
            "gone-TOTAL_FORMS": "0",
            "gone-INITIAL_FORMS": "0",
        }
        for index, (task, chosen) in enumerate(
            [(self.unfiled, project), (filed, filed.project)]
        ):
            data.update(
                {
                    f"new-{index}-id": task.pk,
                    f"new-{index}-due_date": "",
                    f"new-{index}-priority": "medium",
                    f"new-{index}-project": chosen.pk if chosen else "",
                    f"new-{index}-section_path": "S" if chosen else "",
                }
            )
        return self.client.post(
            reverse("todolist:note_review", args=["2026-11-22"]), data
        )

    def test_tache_sans_projet_ni_chemin(self):
        self.assertIsNone(self.unfiled.project)
        self.assertIsNone(self.unfiled.section)
        self.assertEqual(self.unfiled.note_path, "")
        self.assertEqual(self.unfiled.note_state, Task.NoteState.TO_REVIEW)

    def test_reenregistrer_ne_la_duplique_pas(self):
        process_passages(self.note)

        self.assertEqual(Task.objects.filter(title="appeler Paul").count(), 1)

    def test_dans_le_bilan(self):
        response = self.client.get(reverse("todolist:note_review", args=["2026-11-22"]))

        self.assertContains(response, "appeler Paul")
        self.assertContains(response, "à rattacher à un projet")

    def test_choisir_son_projet_dans_le_bilan(self):
        project = Project.objects.create(name="Q")

        self.review(project)

        self.unfiled.refresh_from_db()
        self.assertEqual(self.unfiled.project, project)
        self.assertEqual(self.unfiled.section.name, "S")
        self.assertEqual(self.unfiled.note_state, Task.NoteState.REVIEWED)

    def test_sans_projet_elle_reste_a_revoir(self):
        response = self.review(None)

        self.assertRedirects(
            response, reverse("note_taking:note_detail", args=[self.note.date])
        )
        self.unfiled.refresh_from_db()
        self.assertEqual(self.unfiled.note_state, Task.NoteState.TO_REVIEW)
        self.assertEqual(
            Task.objects.get(title="rangée").note_state, Task.NoteState.REVIEWED
        )

    def test_page_de_la_tache(self):
        response = self.client.get(
            reverse("todolist:task_detail", args=[self.unfiled.pk])
        )

        self.assertContains(response, "à rattacher à un projet")

    def test_liste_des_taches(self):
        response = self.client.get(reverse("todolist:task_list"))

        self.assertContains(response, "appeler Paul")
        self.assertContains(response, "Sans projet")

    def test_calendrier_des_taches(self):
        self.unfiled.due_date = self.note.date
        self.unfiled.save()

        response = self.client.get(reverse("todolist:index"), {"month": "2026-11"})

        self.assertContains(response, "appeler Paul")


class FiledInNoteTests(TestCase):
    """La ligne est rangée sous un titre dans la note : la tâche aussi (#442)."""

    def setUp(self):
        self.note = Note.objects.create(date="2025-11-24", body="- [ ] Une")
        process_passages(self.note)
        self.task = Task.objects.get()

    def file(self) -> Task:
        self.note.body = "# P\n## A\n- [ ] Une"
        self.note.save()
        process_passages(self.note)
        return Task.objects.get()

    def test_prend_le_projet_et_le_niveau(self):
        task = self.file()

        self.assertEqual(task.pk, self.task.pk)
        self.assertEqual((str(task.project), str(task.section)), ("P", "A"))

    def test_reste_a_revoir(self):
        self.assertEqual(self.file().note_state, Task.NoteState.TO_REVIEW)

    def test_projet_deja_choisi_garde(self):
        self.task.project = Project.objects.create(name="Q")
        self.task.save()

        task = self.file()

        self.assertEqual((str(task.project), task.section), ("Q", None))
