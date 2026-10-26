"""Tâches issues des notes : sans échéance, et page bilan après l'enregistrement
d'une note qui en crée (#239)."""

from datetime import date

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse

from core.models import Project, Subject
from note_taking.models import Note
from note_taking.services import process_note_parts
from todolist.models import Todo

BODY = "# P\n### TODO\n- Première\n- Seconde"


def review_url(note_date: str, *todos: Todo) -> str:
    ids = ",".join(str(todo.pk) for todo in todos)
    return f"{reverse('todolist:note_review', args=[note_date])}?ids={ids}"


class NoDueDateTests(TestCase):
    def test_tache_issue_d_une_note_sans_echeance(self):
        note = Note.objects.create(date="2025-11-24", body=BODY)
        process_note_parts(note)

        self.assertEqual(
            list(Todo.objects.values_list("due_date", flat=True)), [None, None]
        )


class RedirectAfterSaveTests(TestCase):
    def post_new(self, body: str):
        return self.client.post(
            reverse("note_taking:new_note"), {"date": "2025-11-24", "body": body}
        )

    def test_nouvelle_note_qui_cree_des_taches(self):
        response = self.post_new(BODY)

        self.assertRedirects(
            response, review_url("2025-11-24", *Todo.objects.order_by("pk"))
        )

    def test_nouvelle_note_sans_tache(self):
        response = self.post_new("# P\ntexte")

        note = Note.objects.get()
        self.assertRedirects(
            response, reverse("note_taking:note_detail", args=[note.pk])
        )

    def test_modification_seulement_les_taches_creees(self):
        note = Note.objects.create(date="2025-11-24", body="# P\n### TODO\n- Première")
        process_note_parts(note)

        response = self.client.post(
            reverse("note_taking:edit_note", args=[note.pk]),
            {"date": "2025-11-24", "body": BODY},
        )

        self.assertRedirects(
            response, review_url("2025-11-24", Todo.objects.get(title="Seconde"))
        )

    def test_modification_sans_nouvelle_tache(self):
        note = Note.objects.create(date="2025-11-24", body=BODY)
        process_note_parts(note)

        response = self.client.post(
            reverse("note_taking:edit_note", args=[note.pk]),
            {"date": "2025-11-24", "body": BODY + "\n\n# Q\ntexte"},
        )

        self.assertRedirects(
            response, reverse("note_taking:note_detail", args=[note.pk])
        )

    def test_remplacement_par_le_fichier_source(self):
        note = Note.objects.create(date="2025-11-24", body="# P\ntexte")
        process_note_parts(note)
        file = SimpleUploadedFile(
            "2025-11-24.qmd", f"---\ndate: 2025-11-24\n---\n{BODY}".encode()
        )

        response = self.client.post(
            reverse("note_taking:update_source_file", args=[note.pk]),
            {"note_update_source_file": file},
        )

        self.assertRedirects(
            response, review_url("2025-11-24", *Todo.objects.order_by("pk"))
        )

    def test_import_tache_creees_dans_le_compte_rendu(self):
        file = SimpleUploadedFile(
            "2025-11-24.qmd", f"---\ndate: 2025-11-24\n---\n{BODY}".encode()
        )

        response = self.client.post(
            reverse("note_taking:import_files"), {"import_files": [file]}
        )

        self.assertContains(response, "2 tâches créées")
        self.assertContains(
            response, review_url("2025-11-24", *Todo.objects.order_by("pk"))
        )


class ReviewPageTests(TestCase):
    def setUp(self):
        self.note = Note.objects.create(date="2025-11-24", body=BODY)
        process_note_parts(self.note)
        self.first, self.second = Todo.objects.order_by("pk")

    def url(self) -> str:
        return review_url("2025-11-24", self.first, self.second)

    def test_liste_les_taches_creees(self):
        response = self.client.get(self.url())

        self.assertContains(response, "Première")
        self.assertContains(response, "Seconde")
        self.assertContains(
            response, reverse("note_taking:note_detail", args=[self.note.pk])
        )

    def test_seulement_les_taches_de_la_note(self):
        other = Todo.objects.create(title="Autre", project=self.first.project)

        response = self.client.get(review_url("2025-11-24", self.first, other))

        self.assertContains(response, "Première")
        self.assertNotContains(response, "Autre")

    def test_enregistrer_les_modifications(self):
        project = Project.objects.create(name="Q")
        subject = Subject.objects.create(name="S")
        data = {
            "form-TOTAL_FORMS": "2",
            "form-INITIAL_FORMS": "2",
            "form-0-id": self.first.pk,
            "form-0-due_date": "2025-12-01",
            "form-0-priority": "high",
            "form-0-project": project.pk,
            "form-0-subject": subject.pk,
            "form-1-id": self.second.pk,
            "form-1-due_date": "",
            "form-1-priority": "medium",
            "form-1-project": self.second.project.pk,
            "form-1-subject": "",
        }

        response = self.client.post(self.url(), data)

        self.assertRedirects(
            response, reverse("note_taking:note_detail", args=[self.note.pk])
        )
        self.first.refresh_from_db()
        self.assertEqual(
            (
                self.first.due_date,
                self.first.priority,
                self.first.project,
                self.first.subject,
            ),
            (date(2025, 12, 1), "high", project, subject),
        )
        self.second.refresh_from_db()
        self.assertIsNone(self.second.due_date)

    def test_sans_tache_retour_a_la_note(self):
        Todo.objects.all().delete()

        response = self.client.get(self.url())

        self.assertRedirects(
            response, reverse("note_taking:note_detail", args=[self.note.pk])
        )

    def test_note_inexistante(self):
        response = self.client.get(review_url("2025-11-25", self.first))

        self.assertEqual(response.status_code, 404)
