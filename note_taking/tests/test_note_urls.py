"""Une note s'adresse par sa date ; l'adresse par id redirige (#273)."""

from datetime import date

from django.test import TestCase
from django.urls import resolve, reverse

from note_taking.models import Note


class NoteUrlTests(TestCase):
    def setUp(self):
        self.note = Note.objects.create(date="2025-11-24", body="# P\nx")

    def test_adresse_par_date(self):
        self.assertEqual(
            reverse("note_taking:note_detail", args=[self.note.date]),
            "/notes/2025-11-24/",
        )
        self.assertEqual(
            reverse("note_taking:edit_note", args=[date(2025, 11, 24)]),
            "/notes/2025-11-24/edit/",
        )

    def test_page_de_la_note(self):
        response = self.client.get("/notes/2025-11-24/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["note"], self.note)

    def test_actions_par_date(self):
        for action in ("export", "edit"):
            with self.subTest(action=action):
                response = self.client.get(f"/notes/2025-11-24/{action}/")
                self.assertEqual(response.status_code, 200)

    def test_date_inconnue_ou_impossible(self):
        for url in ("/notes/2020-01-01/", "/notes/2025-02-30/", "/notes/2025-13-01/"):
            with self.subTest(url=url):
                self.assertEqual(self.client.get(url).status_code, 404)

    def test_date_dans_un_autre_format_refusee(self):
        for url in ("/notes/24-11-2025/", "/notes/2025-1-5/", "/notes/20251124/"):
            with self.subTest(url=url):
                self.assertEqual(self.client.get(url).status_code, 404)

    def test_id_redirige_vers_la_date(self):
        response = self.client.get(f"/notes/{self.note.pk}/")

        self.assertEqual(response.status_code, 308)
        self.assertEqual(response["Location"], "/notes/2025-11-24/")

    def test_id_redirige_aussi_les_actions(self):
        for action in ("export", "edit", "delete"):
            with self.subTest(action=action):
                response = self.client.get(f"/notes/{self.note.pk}/{action}/")
                self.assertEqual(response.status_code, 308)
                self.assertEqual(response["Location"], f"/notes/2025-11-24/{action}/")

    def test_ancienne_vue_markdown_mene_a_la_note(self):
        response = self.client.get(f"/notes/{self.note.pk}/md/")

        self.assertEqual(response["Location"], "/notes/2025-11-24/")

    def test_ancienne_adresse_redirige(self):
        response = self.client.get(f"/note_taking/note/{self.note.pk}/edit/")

        self.assertEqual(response.status_code, 308)
        self.assertEqual(response["Location"], "/notes/2025-11-24/edit/")

    def test_suppression_a_l_ancienne_adresse_garde_la_methode(self):
        response = self.client.post(f"/notes/{self.note.pk}/delete/")
        self.assertEqual(response.status_code, 308)
        self.assertEqual(Note.objects.count(), 1)

        response = self.client.post(response["Location"])

        self.assertEqual(Note.objects.count(), 0)

    def test_id_ou_action_inconnus(self):
        self.assertEqual(self.client.get("/notes/9999/").status_code, 404)
        self.assertEqual(
            self.client.get(f"/notes/{self.note.pk}/inconnue/").status_code, 404
        )

    def test_changer_la_date_change_l_adresse(self):
        response = self.client.post(
            "/notes/2025-11-24/edit/", {"date": "2025-11-25", "body": "# P\nx"}
        )

        self.assertRedirects(
            response, "/notes/2025-11-25/", fetch_redirect_response=False
        )
        self.assertEqual(self.client.get("/notes/2025-11-24/").status_code, 404)
        self.assertEqual(self.client.get("/notes/2025-11-25/").status_code, 200)

    def test_les_pages_gardent_les_prefixes_par_domaine(self):
        for name, prefix in (
            ("note_taking:notes_list", "/notes/"),
            ("note_taking:images_list", "/images/"),
            ("todolist:todo_list", "/tasks/"),
            ("core:projects", "/projects/"),
        ):
            with self.subTest(name=name):
                url = reverse(name)
                self.assertTrue(url.startswith(prefix), url)
                self.assertTrue(url.endswith("/"), url)
                self.assertEqual(resolve(url).view_name, name)
