"""Renommer un projet depuis la page Projets (#170) : le nom, le bilan des titres
`# Ancien` à réécrire dans les notes, puis l'écriture."""

from django.contrib.messages import get_messages
from django.test import TestCase
from django.urls import reverse

from core.models import Project, Section
from note_taking.models import Note, Passage
from note_taking.renaming import project_occurrences
from note_taking.services import process_passages
from todolist.models import Task


class ProjectRenameTestCase(TestCase):
    def setUp(self):
        self.project = Project.objects.create(name="Alpha", color="blue")

    def note(self, body: str, day: str = "2025-11-24") -> Note:
        note = Note.objects.create(date=day, body=body)
        process_passages(note)
        return note

    def url(self) -> str:
        return reverse("core:project_rename", args=[self.project.pk])

    def messages(self, response) -> list[str]:
        return [str(m) for m in get_messages(response.wsgi_request)]


class NameTests(ProjectRenameTestCase):
    def test_formulaire_du_nouveau_nom(self):
        response = self.client.get(self.url())

        self.assertContains(response, "Renommer le projet « Alpha »")
        self.assertContains(response, 'name="name"')
        self.assertNotContains(response, "Bilan")

    def test_nom_vide(self):
        response = self.client.get(self.url(), {"name": "  "})

        self.assertContains(response, "Écrivez le nouveau nom.")
        self.assertNotContains(response, "Bilan")

    def test_meme_nom(self):
        response = self.client.get(self.url(), {"name": " Alpha "})

        self.assertContains(response, "C&#x27;est déjà son nom.")

    def test_nom_d_un_autre_projet_refuse(self):
        Project.objects.create(name="Beta")

        response = self.client.get(self.url(), {"name": "beta"})

        self.assertContains(response, "Un projet « Beta » existe déjà")
        self.assertNotContains(response, "Bilan")

    def test_changer_la_casse_est_permis(self):
        response = self.client.get(self.url(), {"name": "ALPHA"})

        self.assertContains(response, "Bilan")

    def test_lien_depuis_la_page_de_modification(self):
        response = self.client.get(reverse("core:project_edit", args=[self.project.pk]))

        self.assertContains(response, f'href="{self.url()}"')


class OccurrenceTests(ProjectRenameTestCase):
    def test_titres_du_projet_dans_les_notes(self):
        self.note("# Alpha\nx\n# Beta\ny\n# alpha {#a}\nz", "2025-11-24")
        self.note("# Beta\nw", "2025-11-25")
        self.note("```\n# Alpha\n```\n# Alpha\nv", "2025-11-26")

        found = project_occurrences(self.project)

        self.assertEqual(
            [occurrence.where for occurrence in found],
            [
                "Note du 24 novembre 2025, ligne 1",
                "Note du 24 novembre 2025, ligne 5",
                "Note du 26 novembre 2025, ligne 4",
            ],
        )

    def test_bilan_liste_les_titres_et_ce_qui_suit(self):
        self.note("# Alpha\n## Réunion\n- [ ] Écrire")

        response = self.client.get(self.url(), {"name": "Gamma"})

        self.assertContains(response, "Bilan : « Alpha » devient « Gamma »")
        self.assertContains(response, "1 titre à réécrire")
        self.assertContains(response, "Note du 24 novembre 2025, ligne 1")


class WriteTests(ProjectRenameTestCase):
    def test_renomme_le_projet_et_ses_titres(self):
        note = self.note("# Alpha {#top}\n## Réunion\n- [ ] Écrire\n# Beta\ny")
        other = self.note("# alpha\nz", "2025-11-25")
        task = Task.objects.get(note_line_text="Écrire")
        section = Section.objects.get(project=self.project, name="Réunion")

        response = self.client.post(self.url(), {"name": "Gamma"})

        self.assertRedirects(response, reverse("core:projects"))
        self.project.refresh_from_db()
        self.assertEqual(self.project.name, "Gamma")
        self.assertEqual(self.project.color, "blue")
        note.refresh_from_db()
        other.refresh_from_db()
        self.assertEqual(
            note.body, "# Gamma {#top}\n## Réunion\n- [ ] Écrire\n# Beta\ny"
        )
        self.assertEqual(other.body, "# Gamma\nz")
        # Le même projet, avec ses passages, ses niveaux et ses tâches.
        self.assertFalse(Project.objects.filter(name__iexact="alpha").exists())
        self.assertEqual(
            set(Passage.objects.filter(project=self.project).values_list("note", flat=True)),
            {note.pk, other.pk},
        )
        section.refresh_from_db()
        self.assertEqual(section.project, self.project)
        task.refresh_from_db()
        self.assertEqual(task.project, self.project)
        self.assertEqual(task.note_path, "Gamma › Réunion")
        self.assertEqual(Task.objects.filter(note_line_text="Écrire").count(), 1)
        self.assertIn(
            "Le projet « Alpha » est renommé « Gamma ». 2 titres réécrits dans 2 notes.",
            self.messages(response),
        )

    def test_sans_titre_dans_les_notes(self):
        response = self.client.post(self.url(), {"name": "Gamma"})

        self.project.refresh_from_db()
        self.assertEqual(self.project.name, "Gamma")
        self.assertIn("Le projet « Alpha » est renommé « Gamma ».", self.messages(response))

    def test_changer_la_casse(self):
        note = self.note("# Alpha\nx")

        self.client.post(self.url(), {"name": "ALPHA"})

        note.refresh_from_db()
        self.assertEqual(note.body, "# ALPHA\nx")
        self.project.refresh_from_db()
        self.assertEqual(self.project.name, "ALPHA")

    def test_nom_pris_refuse_a_l_ecriture(self):
        self.note("# Alpha\nx")
        Project.objects.create(name="Beta")

        response = self.client.post(self.url(), {"name": "Beta"})

        self.assertEqual(response.status_code, 200)
        self.project.refresh_from_db()
        self.assertEqual(self.project.name, "Alpha")
        self.assertEqual(Note.objects.get().body, "# Alpha\nx")
