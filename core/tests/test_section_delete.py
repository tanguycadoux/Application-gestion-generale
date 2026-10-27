"""Supprimer un niveau de chemin inutilisé (#299)."""

import re

from django.contrib.messages import get_messages
from django.test import TestCase
from django.urls import reverse

from core.models import Project, Section
from core.sections import section_for
from core.templatetags.ui import BUTTON_VARIANTS
from note_taking.models import Note
from note_taking.services import process_note_parts
from todolist.models import Todo


class SectionDeleteTestCase(TestCase):
    def setUp(self):
        self.project = Project.objects.create(name="P")

    def url(self, section: Section) -> str:
        return reverse("core:section_delete", args=[self.project.pk, section.pk])

    def level(self, *names: str) -> Section:
        section = section_for(self.project, names)
        assert section is not None
        return section

    def note(self, body: str) -> Note:
        note = Note.objects.create(date="2025-11-24", body=body)
        process_note_parts(note)
        return note

    def messages(self, response) -> list[tuple[str, str]]:
        return [(m.level_tag, str(m)) for m in get_messages(response.wsgi_request)]


class SectionDeleteTests(SectionDeleteTestCase):
    def test_supprime_un_niveau_inutilise(self):
        section = self.level("A")

        response = self.client.post(self.url(section))

        self.assertRedirects(
            response, reverse("core:project_paths", args=[self.project.pk])
        )
        self.assertFalse(Section.objects.filter(pk=section.pk).exists())
        self.assertEqual(
            self.messages(response), [("success", "Le niveau « A » est supprimé.")]
        )

    def test_supprime_aussi_les_descendants_inutilises(self):
        section = self.level("A")
        self.level("A", "B", "C")
        self.level("Autre")

        response = self.client.post(self.url(section))

        self.assertEqual(
            list(Section.objects.values_list("name", flat=True)), ["Autre"]
        )
        self.assertEqual(
            self.messages(response),
            [("success", "Le niveau « A » est supprimé, avec ses 2 sous-niveaux.")],
        )

    def test_un_seul_sous_niveau(self):
        section = self.level("A")
        self.level("A", "B")

        response = self.client.post(self.url(section))

        self.assertEqual(
            self.messages(response),
            [("success", "Le niveau « A » est supprimé, avec son sous-niveau.")],
        )

    def test_les_freres_et_le_parent_restent(self):
        section = self.level("A", "B")
        self.level("A", "C")

        self.client.post(self.url(section))

        self.assertEqual(
            sorted(Section.objects.values_list("name", flat=True)), ["A", "C"]
        )

    def test_refuse_un_niveau_utilise_par_une_note(self):
        self.note("# P\n## A\nx")
        section = Section.objects.get(name="A")

        response = self.client.post(self.url(section))

        self.assertTrue(Section.objects.filter(pk=section.pk).exists())
        self.assertEqual(
            self.messages(response),
            [
                (
                    "error",
                    "Le niveau « A » est utilisé par 1 note part : "
                    "suppression impossible.",
                )
            ],
        )

    def test_refuse_un_niveau_dont_un_descendant_sert(self):
        self.note("# P\n## A\nx\n### B\ny")
        section = Section.objects.get(name="A")
        self.level("A", "Vide")

        response = self.client.post(self.url(section))

        self.assertEqual(Section.objects.count(), 3)
        self.assertEqual(self.messages(response)[0][0], "error")

    def test_refuse_un_niveau_utilise_par_une_tache(self):
        section = self.level("A")
        Todo.objects.create(title="T", project=self.project, section=section)

        response = self.client.post(self.url(section))

        self.assertTrue(Section.objects.filter(pk=section.pk).exists())
        self.assertEqual(
            self.messages(response),
            [
                (
                    "error",
                    "Le niveau « A » est utilisé par 1 tâche : suppression impossible.",
                )
            ],
        )

    def test_une_tache_ecartee_ne_retient_pas_le_niveau(self):
        section = self.level("A")
        todo = Todo.all_objects.create(
            title="T",
            project=self.project,
            section=section,
            created_from_note=True,
            note_state=Todo.NoteState.DISMISSED,
        )

        self.client.post(self.url(section))

        self.assertFalse(Section.objects.filter(pk=section.pk).exists())
        todo.refresh_from_db()
        self.assertIsNone(todo.section)

    def test_pas_de_page_de_confirmation(self):
        section = self.level("A")

        self.assertEqual(self.client.get(self.url(section)).status_code, 405)
        self.assertTrue(Section.objects.filter(pk=section.pk).exists())

    def test_niveau_d_un_autre_projet(self):
        other = Project.objects.create(name="Q")
        section = section_for(other, ["A"])
        assert section is not None

        response = self.client.post(self.url(section))

        self.assertEqual(response.status_code, 404)
        self.assertTrue(Section.objects.filter(pk=section.pk).exists())


class SectionDeleteButtonTests(SectionDeleteTestCase):
    def html(self) -> str:
        return self.client.get(
            reverse("core:project_paths", args=[self.project.pk])
        ).content.decode()

    def test_niveau_inutilise_confirmation_par_popover(self):
        section = self.level("A")

        form = re.search(
            rf'<form method="post" action="{re.escape(self.url(section))}"'
            r' data-confirm="(?P<message>[^"]*)">(?P<body>.*?)</form>',
            self.html(),
            re.DOTALL,
        )

        assert form is not None
        self.assertEqual(
            form.group("message"), "Supprimer définitivement le niveau « A » ?"
        )
        self.assertIn("csrfmiddlewaretoken", form.group("body"))
        self.assertIn('aria-label="Supprimer le niveau « A »"', form.group("body"))
        self.assertIn(BUTTON_VARIANTS["ghost-danger"], form.group("body"))
        self.assertNotIn("disabled", form.group("body"))

    def test_confirmation_avec_les_sous_niveaux(self):
        self.level("A", "B", "C")

        self.assertIn(
            'data-confirm="Supprimer définitivement le niveau « A » '
            'et ses 2 sous-niveaux ?"',
            self.html(),
        )

    def test_niveau_utilise_bouton_desactive_et_relie_a_la_raison(self):
        self.note("# P\n## A\nx")

        html = self.html()

        self.assertIn('aria-label="Supprimer le niveau « A »"', html)
        described = re.search(r'aria-describedby="([^"]+)"', html)
        assert described is not None
        self.assertIn(f'id="{described.group(1)}"', html)
        self.assertRegex(
            html, r"<button [^>]*disabled aria-label=\"Supprimer le niveau"
        )
