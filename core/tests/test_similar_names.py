"""Doublons probables des projets et des chemins (#374).

Un nom de projet ignore la casse, comme un niveau. Un projet ou un niveau qui vient
d'être créé alors qu'un existant en est proche (casse, accents, pluriel simple) est
signalé à l'enregistrement de la note, sans rien réécrire ; la page Chemins marque
les niveaux frères proches, avec un lien vers leur fusion (#373).
"""

from importlib import import_module
from urllib.parse import parse_qs, urlsplit

from django.contrib.messages import get_messages
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import SimpleTestCase, TestCase, TransactionTestCase
from django.urls import reverse

from core.forms import ProjectForm
from core.models import Project, Section
from core.names import similar_key
from core.projects import project_for
from core.sections import section_for
from note_taking.models import Note, Passage
from note_taking.renaming import find_headings
from note_taking.services import process_passages
from todolist.models import Task


class SimilarKeyTests(SimpleTestCase):
    def test_casse_accents_et_pluriel(self):
        self.assertEqual(
            similar_key("Réunion de chantier"), similar_key("REUNION de Chantier")
        )
        self.assertEqual(
            similar_key("Calculs thermiques"), similar_key("Calcul thermique")
        )
        self.assertEqual(similar_key("Tableaux"), similar_key("tableau"))

    def test_ponctuation_et_espaces(self):
        self.assertEqual(similar_key("Calcul."), similar_key("calcul"))
        self.assertEqual(similar_key("Lot-2 : suivi"), similar_key("lot 2 suivi"))

    def test_noms_differents(self):
        self.assertNotEqual(
            similar_key("Réunion de chantier (suite)"),
            similar_key("Réunion de chantier"),
        )
        # Pas de distance d'édition : une lettre de plus reste un autre nom.
        self.assertNotEqual(similar_key("Lot"), similar_key("Lots2"))
        # Un mot court ne perd pas son « s » : « mois » n'est pas « moi ».
        self.assertNotEqual(similar_key("Mois"), similar_key("Moi"))


class ProjectCaseTests(TestCase):
    def test_project_for_retrouve_l_existant_sans_la_casse(self):
        nord = Project.objects.create(name="Chantier Nord")

        self.assertEqual(project_for("chantier NORD"), (nord, False))
        self.assertEqual(project_for("  Chantier   Nord "), (nord, False))

    def test_project_for_casse_hors_ascii(self):
        etude = Project.objects.create(name="Étude")

        self.assertEqual(project_for("étude"), (etude, False))

    def test_project_for_cree_sinon(self):
        project, created = project_for("Chantier Sud")

        self.assertTrue(created)
        self.assertEqual(project.name, "Chantier Sud")

    def test_la_note_reprend_le_projet_existant(self):
        nord = Project.objects.create(name="Chantier Nord")
        note = Note.objects.create(date="2026-11-23", body="# chantier nord\n## A\nx")

        process_passages(note)

        self.assertEqual(Project.objects.count(), 1)
        self.assertEqual(Passage.objects.get().project, nord)
        section = Section.objects.get()
        self.assertEqual(section.project, nord)

    def test_les_taches_de_la_note_aussi(self):
        nord = Project.objects.create(name="Chantier Nord")
        note = Note.objects.create(date="2026-11-23", body="# CHANTIER NORD\n- [ ] T")

        process_passages(note)

        self.assertEqual(Task.objects.get().project, nord)

    def test_formulaire_refuse_un_nom_a_la_casse_pres(self):
        Project.objects.create(name="Chantier Nord")

        form = ProjectForm({"name": "chantier nord", "color": "orange"})

        self.assertFalse(form.is_valid())
        self.assertIn("Un projet « Chantier Nord » existe déjà.", form.errors["name"])

    def test_le_renommage_trouve_les_titres_sans_la_casse_du_projet(self):
        self.assertEqual(
            [h.number for h in find_headings("# p\n## S", "P", ["S"])], [2]
        )


class ProjectMergeMigrationTests(TransactionTestCase):
    """`0009_merge_projects_by_case` réunit les projets de même nom à la casse près.

    Sur le schéma d'avant (`0008`) : la contrainte de `0010` interdit ensuite deux
    projets de même nom à la casse près."""

    before = [
        ("core", "0008_section_names_without_attributes"),
        ("note_taking", "0042_passages"),
        ("todolist", "0021_task_note_fields_project_optional"),
    ]

    def setUp(self):
        executor = MigrationExecutor(connection)
        executor.migrate([self.before[0]])
        self.apps = executor.loader.project_state(self.before).apps
        self.Project = self.apps.get_model("core", "Project")
        self.Section = self.apps.get_model("core", "Section")
        self.Passage = self.apps.get_model("note_taking", "Passage")
        self.Task = self.apps.get_model("todolist", "Task")
        self.SavedSearch = self.apps.get_model("note_taking", "SavedSearch")
        Note = self.apps.get_model("note_taking", "Note")
        self.note = Note.objects.create(date="2026-11-23")

    def tearDown(self):
        executor = MigrationExecutor(connection)
        executor.loader.build_graph()
        executor.migrate(executor.loader.graph.leaf_nodes())

    def migrate(self) -> None:
        migration = import_module("core.migrations.0009_merge_projects_by_case")
        migration.merge_projects(self.apps, None)

    def project(self, name: str, **fields):
        return self.Project.objects.create(name=name, color="orange", **fields)

    def section(self, project, *names: str):
        parent = None
        for name in names:
            parent = self.Section.objects.get_or_create(
                project=project, parent=parent, name=name
            )[0]
        return parent

    def passage(self, project, section=None):
        return self.Passage.objects.create(
            note=self.note, project=project, section=section
        )

    def test_le_plus_utilise_est_garde(self):
        old = self.project("chantier nord", description="Le chantier")
        used = self.project("Chantier Nord")
        self.passage(used)
        self.passage(used)
        task = self.Task.objects.create(title="T", project=old)
        search = self.SavedSearch.objects.create(name="S")
        search.projects.add(old)

        self.migrate()

        self.assertEqual(
            list(self.Project.objects.values_list("pk", flat=True)), [used.pk]
        )
        task.refresh_from_db()
        self.assertEqual(task.project_id, used.pk)
        self.assertEqual(list(search.projects.values_list("pk", flat=True)), [used.pk])
        used.refresh_from_db()
        self.assertEqual(used.name, "Chantier Nord")
        # Une description vide reprend celle du projet réuni.
        self.assertEqual(used.description, "Le chantier")

    def test_a_egalite_le_plus_ancien(self):
        first = self.project("Alpha")
        second = self.project("ALPHA")
        self.passage(first)
        self.passage(second)

        self.migrate()

        self.assertEqual(
            list(self.Project.objects.values_list("pk", flat=True)), [first.pk]
        )
        self.assertEqual(self.Passage.objects.filter(project=first).count(), 2)

    def test_les_chemins_sont_reunis(self):
        kept = self.project("Nord")
        gone = self.project("nord")
        for _ in range(3):
            self.passage(kept)
        kept_child = self.section(kept, "Réunion", "Compte rendu")
        gone_child = self.section(gone, "réunion", "compte rendu")
        gone_other = self.section(gone, "réunion", "Préparation")
        gone_deep = self.section(gone, "Suivi", "Lot 2")
        moved = self.passage(gone, gone_child)
        task = self.Task.objects.create(title="T", project=gone, section=gone_deep)

        self.migrate()

        moved.refresh_from_db()
        task.refresh_from_db()
        gone_other.refresh_from_db()
        gone_deep.refresh_from_db()
        self.assertEqual((moved.project_id, moved.section_id), (kept.pk, kept_child.pk))
        self.assertEqual(gone_other.project_id, kept.pk)
        self.assertEqual(gone_other.parent_id, kept_child.parent_id)
        self.assertEqual(gone_deep.project_id, kept.pk)
        self.assertEqual(gone_deep.parent.project_id, kept.pk)
        self.assertEqual((task.project_id, task.section_id), (kept.pk, gone_deep.pk))
        self.assertEqual(
            sorted(
                self.Section.objects.filter(parent=None).values_list("name", flat=True)
            ),
            ["Réunion", "Suivi"],
        )

    def test_projets_distincts_inchanges(self):
        self.project("Nord")
        self.project("Nörd")

        self.migrate()

        self.assertEqual(self.Project.objects.count(), 2)


class NoteWarningsTests(TestCase):
    def save(self, body: str, day: str = "2026-11-23") -> tuple[str, ...]:
        note, _ = Note.objects.update_or_create(date=day, defaults={"body": body})
        process_passages(note)
        return note.warnings

    def setUp(self):
        self.save(
            "# Chantier Nord\n## Réunion de chantier\n### Préparation\nx\n"
            "## Calcul thermique\ny",
            day="2026-11-01",
        )

    def test_projet_proche(self):
        warnings = self.save("# Chantier Nörd\nx")

        self.assertEqual(
            warnings,
            (
                "Projet « Chantier Nörd » créé : un projet proche, « Chantier Nord », "
                "existe déjà.",
            ),
        )

    def test_niveau_proche_au_meme_endroit(self):
        warnings = self.save(
            "# Chantier Nord\n## Reunion de chantier\n### Preparation\nx"
        )

        self.assertEqual(
            warnings,
            (
                "Niveau « Reunion de chantier » créé : un niveau proche, « Réunion de "
                "chantier », existe déjà au même endroit (Chantier Nord).",
            ),
        )

    def test_sous_niveau_proche(self):
        warnings = self.save(
            "# Chantier Nord\n## Réunion de chantier\n### Preparations\nx"
        )

        self.assertEqual(
            warnings,
            (
                "Niveau « Preparations » créé : un niveau proche, « Préparation », "
                "existe déjà au même endroit (Chantier Nord › Réunion de chantier).",
            ),
        )

    def test_pluriel(self):
        warnings = self.save("# Chantier Nord\n## Calculs thermiques\nx")

        self.assertEqual(len(warnings), 1)
        self.assertIn("« Calcul thermique »", warnings[0])

    def test_rien_quand_le_niveau_existait(self):
        self.save("# Chantier Nord\n## Reunion de chantier\nx")

        self.assertEqual(self.save("# Chantier Nord\n## Reunion de chantier\nx z"), ())

    def test_rien_dans_un_autre_projet_ou_ailleurs(self):
        self.assertEqual(self.save("# Chantier Sud\n## Calculs thermiques\nx"), ())
        self.assertEqual(
            self.save(
                "# Chantier Nord\n## Lot 2\n### Calcul thermique\nx", "2026-11-24"
            ),
            (),
        )

    def test_rien_pour_un_nom_vraiment_different(self):
        self.assertEqual(
            self.save("# Chantier Nord\n## Réunion de chantier (suite)\nx"), ()
        )

    def test_avertissement_a_l_enregistrement(self):
        response = self.client.post(
            reverse("note_taking:new_note"),
            {
                "date": "2026-11-23",
                "body": "# Chantier Nord\n## Reunion de chantier\nx",
            },
        )

        messages = [str(m) for m in get_messages(response.wsgi_request)]
        self.assertIn("Niveau « Reunion de chantier » créé", messages[1])

    def test_le_texte_de_la_note_n_est_pas_reecrit(self):
        self.save("# Chantier Nörd\n## Reunion de chantier\nx")

        self.assertEqual(
            Note.objects.get(date="2026-11-23").body,
            "# Chantier Nörd\n## Reunion de chantier\nx",
        )


class PathsPageTests(TestCase):
    def setUp(self):
        self.project = Project.objects.create(name="Chantier Nord")
        self.accents = section_for(self.project, ["Reunion de chantier"])
        self.kept = section_for(self.project, ["Réunion de chantier"])
        section_for(self.project, ["Réunion de chantier (suite)"])
        section_for(self.project, ["Lot 2", "Calcul."])
        section_for(self.project, ["Lot 2", "Calculs"])
        # Pas frères : pas proches.
        section_for(self.project, ["Lot 3", "Réunion de chantier"])

    def page(self):
        return self.client.get(reverse("core:project_paths", args=[self.project.pk]))

    def test_niveaux_freres_proches_marques(self):
        rows = {
            (row.section.parent.name if row.section.parent else "", row.section.name): [
                other.name for other in row.similar
            ]
            for row in self.page().context["rows"]
        }

        self.assertEqual(rows[("", "Reunion de chantier")], ["Réunion de chantier"])
        self.assertEqual(rows[("", "Réunion de chantier")], ["Reunion de chantier"])
        self.assertEqual(rows[("", "Réunion de chantier (suite)")], [])
        self.assertEqual(rows[("Lot 2", "Calcul.")], ["Calculs"])
        self.assertEqual(rows[("Lot 3", "Réunion de chantier")], [])

    def test_lien_vers_la_fusion(self):
        html = self.page().content.decode()
        assert self.accents is not None
        url = reverse("core:section_rename", args=[self.project.pk, self.accents.pk])

        self.assertIn("proche de", html)
        self.assertIn(
            f'href="{url}?name=R%C3%A9union+de+chantier"',
            html,
        )
        self.assertIn("Réunir avec «\u00a0Réunion de chantier\u00a0»", html)

    def test_lien_mene_au_bilan_de_la_fusion(self):
        [row] = [r for r in self.page().context["rows"] if r.section == self.accents]
        location = urlsplit(row.similar[0].merge_url)

        self.assertEqual(parse_qs(location.query), {"name": ["Réunion de chantier"]})
