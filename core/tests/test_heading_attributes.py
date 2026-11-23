"""Le nom d'un niveau est le texte du titre sans ses attributs (#367).

`## Réunion de chantier {#reu-12}` est le niveau « Réunion de chantier », comme
l'affiche la note : les attributs Pandoc (`{#id .classe clé=valeur}`) ne sont pas du
texte. `heading_path` garde le titre tel qu'écrit (identité des tâches, #240).
"""

from importlib import import_module

from django.apps import apps
from django.test import SimpleTestCase, TestCase

from core.models import Project, Section
from core.sections import levels
from note_taking.models import Note, Passage, SavedSearch
from note_taking.qmd.parser import heading_name, parse_note
from note_taking.renaming import find_headings, rewrite_titles
from note_taking.search import search_passages
from note_taking.search_query import parse_query
from note_taking.services import process_passages
from todolist.models import Task


class HeadingNameTests(SimpleTestCase):
    def test_attributs_retires(self):
        for title, expected in (
            ("Réunion de chantier {#reu-12}", "Réunion de chantier"),
            ("Bilan {.unnumbered}", "Bilan"),
            ("Bilan {#b .c key=val}", "Bilan"),
            ("Bilan   {-}  ", "Bilan"),
            ("Bilan", "Bilan"),
        ):
            with self.subTest(title=title):
                self.assertEqual(heading_name(title), expected)

    def test_accolades_au_milieu_gardees(self):
        self.assertEqual(heading_name("Ensemble {a} de b"), "Ensemble {a} de b")

    def test_titre_fait_d_attributs_seulement_garde_tel_quel(self):
        """Un niveau sans nom disparaîtrait du chemin : le titre reste son nom."""
        self.assertEqual(heading_name("{#seul}"), "{#seul}")


class ParserTests(SimpleTestCase):
    def test_chemin_sans_attributs_titres_tels_qu_ecrits(self):
        note = parse_note(
            "2026-11-23",
            "# Chantier Nord\n## Réunion de chantier {#reu-12}\n"
            "### Compte rendu {.c}\ntexte",
        )

        [passage] = note.passages
        self.assertEqual(passage.path, ["Réunion de chantier", "Compte rendu"])
        self.assertEqual(
            passage.headings,
            ["Chantier Nord", "Réunion de chantier {#reu-12}", "Compte rendu {.c}"],
        )


class LevelTests(TestCase):
    def note(self, body: str, day: str = "2026-11-23") -> Note:
        note = Note.objects.create(date=day, body=body)
        process_passages(note)
        return note

    def test_un_seul_niveau_avec_ou_sans_attributs(self):
        self.note("# Chantier Nord\n## Réunion de chantier {#reu-12}\nx")
        self.note("# Chantier Nord\n## Réunion de chantier\ny", day="2026-11-24")

        self.assertEqual(
            list(Section.objects.values_list("name", flat=True)),
            ["Réunion de chantier"],
        )
        passage = Passage.objects.get(note__date="2026-11-23")
        self.assertEqual(
            passage.heading_path, "Chantier Nord › Réunion de chantier {#reu-12}"
        )

    def test_la_recherche_par_chemin_trouve_le_titre_a_attributs(self):
        self.note(
            "# Chantier Nord\n## Réunion de chantier {#reu-12}\n### Compte rendu\nx"
        )

        found = search_passages(parse_query('chemin:"réunion de chantier"'))

        self.assertEqual(len(list(found)), 1)

    def test_la_tache_garde_le_titre_tel_qu_ecrit_dans_son_chemin(self):
        self.note("# P\n## Réunion {#r}\n- [ ] Relancer")

        task = Task.objects.get()
        self.assertEqual(task.note_path, "P › Réunion {#r}")
        assert task.section is not None
        self.assertEqual(levels(task.section), ["Réunion"])


class RenamingTests(SimpleTestCase):
    def test_le_titre_a_attributs_est_ce_niveau(self):
        found = find_headings("# P\n## Réunion {#reu-12}\n## Réunion", "P", ["réunion"])

        self.assertEqual([h.number for h in found], [2, 3])

    def test_la_reecriture_garde_les_attributs(self):
        self.assertEqual(
            rewrite_titles("# P\n## Ancien {#reu-12 .c}\r\nx", [2], "Nouveau"),
            "# P\n## Nouveau {#reu-12 .c}\r\nx",
        )


class MigrationTests(TestCase):
    """`0008_section_names_without_attributes` corrige les niveaux existants."""

    def migrate(self) -> None:
        migration = import_module(
            "core.migrations.0008_section_names_without_attributes"
        )
        migration.strip_attributes(apps, None)

    def setUp(self):
        self.project = Project.objects.create(name="P")
        self.note = Note.objects.create(date="2026-11-23")

    def section(self, name: str, parent: Section | None = None) -> Section:
        return Section.objects.create(project=self.project, parent=parent, name=name)

    def test_niveau_seul_renomme(self):
        alone = self.section("Bilan {.unnumbered}")

        self.migrate()

        alone.refresh_from_db()
        self.assertEqual(alone.name, "Bilan")

    def test_fusion_avec_le_niveau_sans_attributs(self):
        kept = self.section("réunion")
        gone = self.section("Réunion {#reu-12}")
        kept_child = self.section("Compte rendu", kept)
        gone_child = self.section("compte rendu", gone)
        other_child = self.section("Préparation", gone)
        passage = Passage.objects.create(
            note=self.note, project=self.project, section=gone
        )
        child_passage = Passage.objects.create(
            note=self.note, project=self.project, section=gone_child
        )
        task = Task.objects.create(title="T", project=self.project, section=gone)
        search = SavedSearch.objects.create(name="S")
        search.sections.add(gone)

        self.migrate()

        self.assertFalse(
            Section.objects.filter(pk__in=[gone.pk, gone_child.pk]).exists()
        )
        passage.refresh_from_db()
        child_passage.refresh_from_db()
        task.refresh_from_db()
        other_child.refresh_from_db()
        self.assertEqual(passage.section_id, kept.pk)
        self.assertEqual(child_passage.section_id, kept_child.pk)
        self.assertEqual(task.section_id, kept.pk)
        self.assertEqual(other_child.parent_id, kept.pk)
        self.assertEqual(list(search.sections.all()), [kept])
        kept.refresh_from_db()
        self.assertEqual(kept.name, "réunion")

    def test_deux_niveaux_a_attributs_sans_niveau_nu(self):
        first = self.section("Réunion {#a}")
        second = self.section("Réunion {#b}")

        self.migrate()

        self.assertEqual(
            list(Section.objects.values_list("pk", "name")), [(first.pk, "Réunion")]
        )
        self.assertFalse(Section.objects.filter(pk=second.pk).exists())

    def test_sous_niveaux_a_attributs(self):
        parent = self.section("A")
        child = self.section("B {#b}", parent)

        self.migrate()

        child.refresh_from_db()
        self.assertEqual(child.name, "B")

    def test_niveaux_sans_attributs_inchanges(self):
        plain = self.section("Ensemble {a} de b")

        self.migrate()

        plain.refresh_from_db()
        self.assertEqual(plain.name, "Ensemble {a} de b")
