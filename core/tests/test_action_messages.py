"""Un message de confirmation par action, de la même forme partout (#192).

« L'objet « nom » est créé / modifié / supprimé. », au présent ; une note se
nomme par sa date au format moyen.
"""

import shutil
import tempfile
import unittest

from django.contrib.messages import get_messages
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse

from core.models import Project
from images.services import import_image
from images.tests.files import image_file
from note_taking.models import Note
from todolist.models import Todo

MEDIA_ROOT = tempfile.mkdtemp()


@override_settings(MEDIA_ROOT=MEDIA_ROOT)
class ActionMessagesTests(TestCase):
    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(MEDIA_ROOT, ignore_errors=True)

    def setUp(self):
        self.project = Project.objects.create(name="ASTERICS")

    def messages(self, response) -> list[str]:
        return [str(m) for m in get_messages(response.wsgi_request)]

    def post(self, name: str, *args, data=None) -> list[str]:
        return self.messages(self.client.post(reverse(name, args=args), data or {}))

    # Projets

    def test_projet_modifie(self):
        self.assertEqual(
            self.post("core:project_edit", self.project.pk, data={"color": "sky"}),
            ["Le projet « ASTERICS » est modifié."],
        )

    # Tâches

    def task_data(self, title: str) -> dict:
        return {
            "title": title,
            "project": self.project.pk,
            "priority": "medium",
            "progress": 0,
        }

    @unittest.expectedFailure
    def test_tache_creee(self):
        self.assertEqual(
            self.post("todolist:todo_create", data=self.task_data("Relire")),
            ["La tâche « Relire » est créée."],
        )

    @unittest.expectedFailure
    def test_tache_modifiee(self):
        task = Todo.objects.create(title="Relire", project=self.project)

        self.assertEqual(
            self.post("todolist:todo_edit", task.pk, data=self.task_data("Relu")),
            ["La tâche « Relu » est modifiée."],
        )

    @unittest.expectedFailure
    def test_tache_supprimee(self):
        task = Todo.objects.create(title="Relire", project=self.project)

        self.assertEqual(
            self.post("todolist:todo_delete", task.pk),
            ["La tâche « Relire » est supprimée."],
        )

    @unittest.expectedFailure
    def test_tache_supprimee_avec_ses_sous_taches(self):
        task = Todo.objects.create(title="Relire", project=self.project)
        Todo.objects.create(title="A", project=self.project, parent=task)
        Todo.objects.create(title="B", project=self.project, parent=task)

        self.assertEqual(
            self.post("todolist:todo_delete", task.pk),
            ["La tâche « Relire » et ses 2 sous-tâches sont supprimées."],
        )

    # Notes

    @unittest.expectedFailure
    def test_note_creee(self):
        self.assertEqual(
            self.post(
                "note_taking:new_note", data={"date": "2025-11-24", "body": "# P\nx"}
            ),
            ["La note du 24 novembre 2025 est créée."],
        )

    @unittest.expectedFailure
    def test_note_modifiee(self):
        note = Note.objects.create(date="2025-11-24", body="# P\nx")

        self.assertEqual(
            self.post(
                "note_taking:edit_note",
                note.pk,
                data={"date": "2025-11-24", "body": "# P\ny"},
            ),
            ["La note du 24 novembre 2025 est modifiée."],
        )

    def test_note_non_traitee_sans_message_de_succes(self):
        messages = self.post(
            "note_taking:new_note",
            data={"date": "2025-11-24", "body": "# P\n![a](absente.png)"},
        )

        self.assertEqual(len(messages), 1)
        self.assertIn("n'a pas pu être traité", messages[0])

    @unittest.expectedFailure
    def test_note_modifiee_par_son_fichier_source(self):
        note = Note.objects.create(date="2025-11-24", body="# P\nx")
        file = SimpleUploadedFile(
            "2025-11-24.qmd", b"---\ndate: 2025-11-24\n---\n# P\ny"
        )

        self.assertEqual(
            self.post(
                "note_taking:update_source_file",
                note.pk,
                data={"note_update_source_file": file},
            ),
            ["La note du 24 novembre 2025 est modifiée."],
        )

    @unittest.expectedFailure
    def test_note_supprimee(self):
        note = Note.objects.create(date="2025-11-24", body="# P\nx")

        self.assertEqual(
            self.post("note_taking:delete_note", note.pk),
            ["La note du 24 novembre 2025 est supprimée."],
        )

    # Images

    @unittest.expectedFailure
    def test_image_supprimee(self):
        image = import_image(image_file("banc.png"))

        self.assertEqual(
            self.post("note_taking:delete_image", image.pk),
            ["L'image « banc.png » est supprimée."],
        )
