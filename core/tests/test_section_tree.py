"""L'arbre des chemins d'un projet : niveaux, indentation, compteurs (#299)."""

import re
from unittest import expectedFailure

from django.test import TestCase
from django.urls import reverse

from core.models import Project
from core.section_tree import section_tree
from core.sections import section_for
from note_taking.models import Note
from note_taking.services import process_passages
from todolist.models import Task


class TreeTestCase(TestCase):
    def setUp(self):
        self.project = Project.objects.create(name="P")

    def note(self, body: str, day: str = "2025-11-24") -> Note:
        note = Note.objects.create(date=day, body=body)
        process_passages(note)
        return note


class SectionTreeTests(TreeTestCase):
    def rows(self) -> list[tuple[str, int, str]]:
        return [
            (row.section.name, row.depth, row.usage)
            for row in section_tree(self.project)
        ]

    def test_parents_d_abord_freres_tries_sans_casse(self):
        section_for(self.project, ["b", "Y"])
        section_for(self.project, ["A", "z"])
        section_for(self.project, ["A", "X"])

        self.assertEqual(
            [(name, depth) for name, depth, _ in self.rows()],
            [("A", 0), ("X", 1), ("z", 1), ("b", 0), ("Y", 1)],
        )

    def test_niveau_inutilise(self):
        section_for(self.project, ["A"])

        self.assertEqual(self.rows(), [("A", 0, "")])

    def test_compte_les_passages_du_niveau_et_de_ses_descendants(self):
        """#362 : les passages s'appellent des passages dans l'interface."""
        self.note("# P\n## A\nx\n### B\ny\n### C\nz")

        self.assertEqual(
            self.rows(),
            [
                ("A", 0, "3 passages"),
                ("B", 1, "1 passage"),
                ("C", 1, "1 passage"),
            ],
        )

    def test_compte_aussi_les_taches(self):
        self.note("# P\n## A\n- [ ] Une\n### B\n- [ ] Deux\n- [ ] Trois")

        rows = {name: usage for name, _, usage in self.rows()}

        self.assertEqual(rows["A"], "2 passages et 3 tâches")
        self.assertEqual(rows["B"], "1 passage et 2 tâches")

    def test_tache_saisie_a_la_main_comptee(self):
        section = section_for(self.project, ["A"])
        Task.objects.create(title="T", project=self.project, section=section)

        self.assertEqual(self.rows(), [("A", 0, "1 tâche")])

    def test_tache_ecartee_non_comptee(self):
        section = section_for(self.project, ["A"])
        Task.all_objects.create(
            title="T",
            project=self.project,
            section=section,
            created_from_note=True,
            note_state=Task.NoteState.DISMISSED,
        )

        self.assertEqual(self.rows(), [("A", 0, "")])

    def test_autre_projet_non_compte(self):
        other = Project.objects.create(name="Q")
        section_for(other, ["Z"])
        section_for(self.project, ["A"])

        self.assertEqual([name for name, _, _ in self.rows()], ["A"])

    def test_nombre_de_requetes_constant(self):
        for index in range(12):
            section_for(self.project, [f"N{index}", "Sous"])

        with self.assertNumQueries(1):
            section_tree(self.project)


class TreePageTests(TreeTestCase):
    def url(self, project=None) -> str:
        return reverse("core:project_paths", args=[(project or self.project).pk])

    def test_page_avec_le_projet_et_ses_niveaux(self):
        self.note("# P\n## Réunion\nx\n### Suite\ny")

        response = self.client.get(self.url())

        self.assertContains(response, '<h1 class="flex-1">Chemins de P</h1>', html=True)
        self.assertContains(response, "Réunion")
        self.assertContains(response, "2 passages")
        self.assertContains(response, "Suite")

    def test_indentation_par_niveau(self):
        section_for(self.project, ["A", "B", "C"])

        html = self.client.get(self.url()).content.decode()

        rows = re.findall(r'<li class="flex items-center gap-2 py-1 (pl-\d+)">', html)
        self.assertEqual(rows, ["pl-0", "pl-6", "pl-12"])

    def test_lien_de_renommage_par_niveau(self):
        section = section_for(self.project, ["A"])
        assert section is not None

        html = self.client.get(self.url()).content.decode()

        url = reverse("core:section_rename", args=[self.project.pk, section.pk])
        self.assertIn(f'href="{url}"', html)
        self.assertIn('aria-label="Renommer le niveau « A »"', html)

    def test_inutilise(self):
        section_for(self.project, ["A"])

        self.assertContains(self.client.get(self.url()), "inutilisé")

    @expectedFailure
    def test_compteurs_en_liens_vers_les_passages_et_les_taches(self):
        """#375 : la recherche et la liste des tâches filtrées sur le niveau. La liste
        montre aussi les tâches terminées, que le compteur compte."""
        section = section_for(self.project, ["A"])
        assert section is not None
        self.note("# P\n## A\n- [ ] Une\n- [ ] Deux")

        html = self.client.get(self.url()).content.decode()

        self.assertInHTML(
            f'<a href="{reverse("note_taking:notes_search")}?subjects={section.pk}"'
            ' aria-label="1 passage du niveau « A »">1 passage</a>',
            html,
        )
        self.assertInHTML(
            f'<a href="{reverse("todolist:task_list")}?path={section.pk}&amp;state=all"'
            ' aria-label="2 tâches du niveau « A »">2 tâches</a>',
            html,
        )

    @expectedFailure
    def test_la_cible_d_un_compteur_montre_ce_qu_il_compte(self):
        """#375 : descendants compris, tâches terminées comprises."""
        self.note("# P\n## A\nx\n### B\n- [ ] Une")
        Task.objects.filter(title="Une").update(done=True, progress=100)
        row = section_tree(self.project)[0]

        passages, tasks = [self.client.get(link.url) for link in row.usages]

        self.assertContains(passages, "2 passages dans 1 note")
        self.assertContains(tasks, ">Une</a>")

    def test_niveau_inutilise_sans_lien(self):
        section_for(self.project, ["A"])

        html = self.client.get(self.url()).content.decode()

        self.assertNotIn("?subjects=", html)
        self.assertNotIn("?path=", html)

    def test_projet_sans_niveau(self):
        self.assertContains(self.client.get(self.url()), "Aucun niveau")

    def test_projet_inconnu(self):
        self.assertEqual(
            self.client.get(reverse("core:project_paths", args=[999])).status_code, 404
        )

    def test_lien_depuis_la_page_des_projets(self):
        html = self.client.get(reverse("core:projects")).content.decode()

        self.assertIn(f'href="{self.url()}"', html)
        self.assertIn('aria-label="Chemins du projet"', html)
