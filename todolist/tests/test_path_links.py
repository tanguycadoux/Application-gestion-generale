"""Le chemin d'une tâche mène à ses voisines, sa note d'origine s'ouvre à sa section,
et la liste des tâches montre les chemins (#375)."""

import json
import re

from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from core.models import Project, Section
from core.sections import path_labels, section_for
from note_taking.models import Note
from note_taking.services import process_passages
from todolist.models import Task


class LinksTestCase(TestCase):
    def setUp(self):
        self.project = Project.objects.create(name="P")

    def section(self, *names: str, project: Project | None = None) -> Section:
        section = section_for(project or self.project, names)
        assert section is not None
        return section

    def task(self, title: str, **fields) -> Task:
        return Task.objects.create(title=title, project=self.project, **fields)

    def detail(self, task: Task) -> str:
        return self.client.get(
            reverse("todolist:task_detail", args=[task.pk])
        ).content.decode()


class DetailPathTests(LinksTestCase):
    def test_chaque_niveau_mene_a_ses_taches(self):
        leaf = self.section("Réunion", "Préparation")
        task = self.task("T", section=leaf)

        html = self.detail(task)

        url = reverse("todolist:task_list")
        self.assertRegex(
            html,
            rf"<dt[^>]*>Chemin</dt>\s*<dd>"
            rf'<a href="{url}\?path={leaf.parent_id}">Réunion</a> › '
            rf'<a href="{url}\?path={leaf.pk}">Préparation</a></dd>',
        )

    def test_sans_chemin(self):
        self.assertRegex(
            self.detail(self.task("T")), r"<dt[^>]*>Chemin</dt>\s*<dd>Aucun</dd>"
        )


class OriginNoteTests(LinksTestCase):
    def note(self, body: str) -> Note:
        note = Note.objects.create(date="2025-11-24", body=body)
        process_passages(note)
        return note

    def rewrite(self, note: Note, body: str) -> None:
        note.body = body
        note.save()
        process_passages(note)

    def origin(self, title: str) -> str:
        """L'adresse de la note d'origine dans la fiche de cette tâche."""
        html = self.detail(Task.objects.get(title=title))
        found = re.search(r"Note d'origine</dt>\s*<dd><a href=\"([^\"]*)\"", html)
        assert found is not None
        return found[1]

    def url(self, anchor: str = "") -> str:
        return reverse("note_taking:note_detail", args=["2025-11-24"]) + anchor

    def test_ouverte_au_titre_de_la_section(self):
        self.note("# P\n## Réunion\n### Suite\n- [ ] Une")

        self.assertEqual(self.origin("Une"), self.url("#suite"))

    def test_titre_repete_sa_propre_occurrence(self):
        self.note("# P\n## A\n- [ ] Une\n## B\nx\n## A\n- [ ] Deux")

        self.assertEqual(self.origin("Une"), self.url("#a"))
        self.assertEqual(self.origin("Deux"), self.url("#a-1"))

    def test_sous_tache_et_case_imbriquee(self):
        self.note("# P\n## A\n- un point\n    - [ ] Une")

        self.assertEqual(self.origin("Une"), self.url("#a"))

    def test_case_cochee_dans_la_note(self):
        """La ligne n'est plus une tâche : la section reste la bonne."""
        note = self.note("# P\n## A\n- [ ] Une")
        self.rewrite(note, "# P\n## A\n- [x] Une")

        self.assertEqual(self.origin("Une"), self.url("#a"))

    def test_section_disparue_le_niveau_au_dessus(self):
        note = self.note("# P\nx\n## A\n- [ ] Une")
        self.rewrite(note, "# P\nx")

        self.assertEqual(self.origin("Une"), self.url("#p"))

    def test_texte_sans_projet_en_haut_de_la_note(self):
        self.note("- [ ] Une")

        self.assertEqual(self.origin("Une"), self.url())


class ListPathTests(LinksTestCase):
    def path_of(self, task: Task, html: str | None = None) -> str:
        """Le chemin affiché sous le titre d'une tâche de la liste."""
        if html is None:
            html = self.client.get(reverse("todolist:task_list")).content.decode()
        row = html[html.index(f'data-task-id="{task.pk}"') :].split("</tr>")[0]
        found = re.search(r"<p[^>]*>(.*?)</p>", row, re.DOTALL)
        return found[1] if found else ""

    def test_chemin_sous_le_titre(self):
        task = self.task("T", section=self.section("Réunion", "Préparation"))

        self.assertEqual(self.path_of(task), "Réunion › Préparation")

    def test_sans_chemin(self):
        self.assertEqual(self.path_of(self.task("T")), "")

    def test_sous_tache_seulement_si_le_chemin_differe_du_parent(self):
        section = self.section("A")
        parent = self.task("Parent", section=section)
        same = self.task("Même", section=section, parent=parent)
        other = self.task("Autre", section=self.section("A", "B"), parent=parent)
        none = self.task("Sans", parent=parent)

        html = self.client.get(reverse("todolist:task_list")).content.decode()

        self.assertEqual(self.path_of(parent, html), "A")
        self.assertEqual(self.path_of(same, html), "")
        self.assertEqual(self.path_of(other, html), "A › B")
        self.assertEqual(self.path_of(none, html), "")

    def test_sous_taches_du_detail(self):
        section = self.section("A")
        parent = self.task("Parent", section=section)
        same = self.task("Même", section=section, parent=parent)
        other = self.task("Autre", section=self.section("B"), parent=parent)

        html = self.detail(parent)

        self.assertEqual(self.path_of(same, html), "")
        self.assertEqual(self.path_of(other, html), "B")

    def test_ligne_remplacee_apres_une_case_cochee(self):
        task = self.task("T", section=self.section("A"))

        response = self.client.post(
            reverse("todolist:task_toggle", args=[task.pk]),
            json.dumps({"completed": True}),
            content_type="application/json",
        )

        self.assertEqual(self.path_of(task, response.json()["rows"][str(task.pk)]), "A")

    def test_chemin_echappe(self):
        task = self.task("T", section=self.section("<b>R&D</b>"))

        self.assertEqual(self.path_of(task), "&lt;b&gt;R&amp;D&lt;/b&gt;")

    def queries(self) -> int:
        with CaptureQueriesContext(connection) as captured:
            self.client.get(reverse("todolist:task_list"))
        return len(captured)

    def test_nombre_de_requetes_constant(self):
        self.task("T", section=self.section("N", "Sous"))
        before = self.queries()
        for index in range(8):
            self.task(f"T{index}", section=self.section(f"N{index}", "Sous", "Sous"))

        self.assertEqual(self.queries(), before)


class PathLabelsTests(LinksTestCase):
    def test_sans_le_projet(self):
        leaf = self.section("A", "B")

        with self.assertNumQueries(1):
            labels = path_labels(with_project=False)

        self.assertEqual(labels[leaf.pk], "A › B")
