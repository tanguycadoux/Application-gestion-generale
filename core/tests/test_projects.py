"""Tests des projets : couleur, pastille et page de gestion (#162)."""

from django.contrib.messages import get_messages
from django.template import Context, Template
from django.test import TestCase
from django.urls import reverse

from core.models import Project
from note_taking.models import Note
from note_taking.services import process_note_parts
from todolist.models import Todo

FAMILIES = [
    "orange",
    "yellow",
    "lime",
    "emerald",
    "teal",
    "cyan",
    "sky",
    "indigo",
    "violet",
    "purple",
    "fuchsia",
    "pink",
    "rose",
]


def render(source: str, **context) -> str:
    return Template("{% load ui %}" + source).render(Context(context))


class ProjectColorTests(TestCase):
    def test_familles_proposees(self):
        """Hors gris et hors familles qui ont un rôle (blue, red, amber, green)."""
        self.assertEqual(
            [value for value, _ in Project._meta.get_field("color").choices], FAMILIES
        )

    def test_couleur_la_moins_utilisee_par_defaut(self):
        """Un projet créé sans couleur (import d'une note, d'une tâche) en reçoit une."""
        Project.objects.create(name="A", color="orange")
        Project.objects.create(name="B", color="lime")

        project = Project.objects.create(name="C")

        self.assertEqual(project.color, "yellow")

    def test_projet_cree_par_une_note(self):
        note = Note.objects.create(date="2025-11-24", body="# Nouveau\nx")

        process_note_parts(note)

        self.assertEqual(Project.objects.get(name="Nouveau").color, "orange")


class ProjectBadgeTests(TestCase):
    def test_pastille(self):
        project = Project.objects.create(name="ASTERICS", color="teal")

        self.assertHTMLEqual(
            render("{% project_badge p %}", p=project),
            '<span class="inline-flex items-center gap-1.5">'
            '<span class="size-2.5 shrink-0 rounded-full bg-teal-500"'
            ' aria-hidden="true"></span>ASTERICS</span>',
        )

    def test_pastille_sans_projet(self):
        self.assertEqual(render("{% project_badge p %}", p=None).strip(), "")


class ProjectPagesTests(TestCase):
    def create_projects(self):
        self.used = Project.objects.create(name="Utilisé", color="teal")
        note = Note.objects.create(date="2025-11-24", body="# Utilisé\nx")
        process_note_parts(note)
        Todo.objects.create(title="T", project=self.used)
        self.unused = Project.objects.create(
            name="Libre", color="rose", description="Pour plus tard"
        )

    def messages(self, response) -> list[str]:
        return [str(m) for m in get_messages(response.wsgi_request)]

    def test_lien_depuis_l_accueil_general(self):
        self.create_projects()
        html = self.client.get("/").content.decode()

        self.assertIn(f'href="{reverse("core:projects")}"', html)

    def test_liste(self):
        self.create_projects()
        html = self.client.get(reverse("core:projects")).content.decode()

        self.assertIn("<title>Liste des projets · Projets</title>", html)
        self.assertIn("bg-teal-500", html)
        self.assertIn("Pour plus tard", html)
        self.assertIn("1 note", html)
        self.assertIn("1 tâche", html)

    def test_creation(self):
        self.create_projects()
        response = self.client.post(
            reverse("core:project_create"),
            {"name": "Nouveau", "color": "violet", "description": "D"},
        )

        self.assertRedirects(response, reverse("core:projects"))
        project = Project.objects.get(name="Nouveau")
        self.assertEqual((project.color, project.description), ("violet", "D"))
        self.assertEqual(self.messages(response), ["Le projet « Nouveau » est créé."])

    def test_creation_d_un_nom_deja_pris_refusee(self):
        self.create_projects()
        response = self.client.post(
            reverse("core:project_create"), {"name": "Libre", "color": "violet"}
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(Project.objects.filter(name="Libre").count(), 1)

    def test_modification_de_la_couleur_et_de_la_description(self):
        self.create_projects()
        url = reverse("core:project_edit", args=[self.unused.pk])

        form_html = self.client.get(url).content.decode()
        response = self.client.post(url, {"color": "sky", "description": "Autre"})

        self.assertNotIn('name="name"', form_html)
        self.assertRedirects(response, reverse("core:projects"))
        self.unused.refresh_from_db()
        self.assertEqual(
            (self.unused.name, self.unused.color, self.unused.description),
            ("Libre", "sky", "Autre"),
        )

    def test_suppression_d_un_projet_inutilise(self):
        self.create_projects()
        url = reverse("core:project_delete", args=[self.unused.pk])

        self.assertEqual(self.client.get(url).status_code, 405)
        response = self.client.post(url)

        self.assertRedirects(response, reverse("core:projects"))
        self.assertFalse(Project.objects.filter(pk=self.unused.pk).exists())
        self.assertEqual(self.messages(response), ["Le projet « Libre » est supprimé."])

    def test_suppression_refusee_si_le_projet_est_utilise(self):
        self.create_projects()
        response = self.client.post(reverse("core:project_delete", args=[self.used.pk]))

        self.assertRedirects(response, reverse("core:projects"))
        self.assertTrue(Project.objects.filter(pk=self.used.pk).exists())
        self.assertEqual(
            self.messages(response),
            ["Le projet « Utilisé » est utilisé par 1 note et 1 tâche."],
        )

    def test_bouton_desactive_avec_la_raison(self):
        self.create_projects()
        html = self.client.get(reverse("core:projects")).content.decode()

        self.assertIn("Utilisé par 1 note et 1 tâche.", html)
        self.assertIn(
            'data-confirm="Supprimer définitivement le projet « Libre » ?"', html
        )
