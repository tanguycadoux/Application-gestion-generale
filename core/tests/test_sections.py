"""Chemins sous un projet : le modèle `Section` et ses services (#287, #295).

Un chemin est un arbre de lignes : un « / » d'un titre n'est pas un séparateur, et
un niveau est unique sous son parent, casse ignorée. À la saisie « / » sépare les
niveaux et « // » est un « / » littéral.
"""

from django.core.exceptions import ValidationError
from django.db import IntegrityError, connection, transaction
from django.db.migrations.executor import MigrationExecutor
from django.test import TestCase, TransactionTestCase

from core.forms import SectionChoiceField
from core.models import Project, Section
from core.sections import (
    ancestors_and_self,
    forget_unused_sections,
    join_path,
    label,
    levels,
    path_labels,
    section_for,
    split_path,
    subtree,
    with_ancestors,
    with_descendants,
)
from note_taking.models import Note, NotePart
from todolist.models import Todo


class SplitPathTests(TestCase):
    def test_niveaux_separes_par_une_barre(self):
        self.assertEqual(split_path("Réunion/Préparation"), ["Réunion", "Préparation"])

    def test_espaces_reduits_et_niveaux_vides_ignores(self):
        self.assertEqual(
            split_path("  Réunion  d'avancement / / Préparation /"),
            ["Réunion d'avancement", "Préparation"],
        )

    def test_double_barre_est_une_barre_litterale(self):
        self.assertEqual(
            split_path("Rapport RT17//A/Suite"), ["Rapport RT17/A", "Suite"]
        )

    def test_barre_litterale_en_fin_de_niveau(self):
        self.assertEqual(split_path("A///B"), ["A/", "B"])

    def test_texte_vide(self):
        self.assertEqual(split_path(""), [])
        self.assertEqual(split_path(" / "), [])

    def test_join_relit_a_l_identique(self):
        for names in (
            ["Réunion", "Préparation"],
            ["Rapport RT17/A", "Suite"],
            ["A/", "B"],
            ["/A"],
            ["Seul"],
        ):
            with self.subTest(names=names):
                self.assertEqual(split_path(join_path(names)), names)


class SectionForTests(TestCase):
    def setUp(self):
        self.project = Project.objects.create(name="P")

    def test_cree_le_chemin_niveau_par_niveau(self):
        section = section_for(self.project, ["Réunion", "Préparation"])

        assert section is not None
        self.assertEqual(levels(section), ["Réunion", "Préparation"])
        self.assertEqual(Section.objects.count(), 2)
        self.assertEqual(section.project, self.project)
        self.assertEqual(section.parent.parent, None)

    def test_chemin_vide(self):
        self.assertIsNone(section_for(self.project, []))
        self.assertIsNone(section_for(self.project, ["", "  "]))

    def test_reprend_le_chemin_connu(self):
        first = section_for(self.project, ["Réunion", "Préparation"])

        second = section_for(self.project, ["Réunion", "Préparation"])

        self.assertEqual(first, second)
        self.assertEqual(Section.objects.count(), 2)

    def test_casse_ignoree_premiere_ecriture_gardee(self):
        first = section_for(self.project, ["Réunion", "Préparation"])

        second = section_for(self.project, ["réunion", "PRÉPARATION"])

        self.assertEqual(first, second)
        assert second is not None
        self.assertEqual(levels(second), ["Réunion", "Préparation"])

    def test_parent_connu_enfant_nouveau(self):
        section_for(self.project, ["Réunion", "Préparation"])

        section_for(self.project, ["réunion", "Suite"])

        self.assertEqual(Section.objects.filter(name="Réunion").count(), 1)
        self.assertEqual(Section.objects.count(), 3)

    def test_meme_nom_sous_deux_parents(self):
        a = section_for(self.project, ["A", "Notes"])
        b = section_for(self.project, ["B", "Notes"])

        self.assertNotEqual(a, b)

    def test_meme_nom_sous_deux_projets(self):
        other = Project.objects.create(name="Q")

        self.assertNotEqual(
            section_for(self.project, ["Réunion"]), section_for(other, ["Réunion"])
        )

    def test_barre_dans_un_titre_reste_un_seul_niveau(self):
        section = section_for(self.project, ["Rapport RT17/A"])

        assert section is not None
        self.assertEqual(levels(section), ["Rapport RT17/A"])
        self.assertEqual(Section.objects.count(), 1)


class SectionModelTests(TestCase):
    def setUp(self):
        self.project = Project.objects.create(name="P")

    def test_deux_racines_de_meme_nom_refusees(self):
        """La base ne replie que l'ASCII ; `section_for` compare en Python pour le reste."""
        Section.objects.create(project=self.project, name="Notes")

        with self.assertRaises(IntegrityError), transaction.atomic():
            Section.objects.create(project=self.project, name="NOTES")

    def test_deux_enfants_de_meme_nom_refuses(self):
        parent = Section.objects.create(project=self.project, name="A")
        Section.objects.create(project=self.project, parent=parent, name="Suite")

        with self.assertRaises(IntegrityError), transaction.atomic():
            Section.objects.create(project=self.project, parent=parent, name="suite")

    def test_racine_de_meme_nom_sous_un_autre_projet(self):
        other = Project.objects.create(name="Q")
        Section.objects.create(project=self.project, name="Réunion")

        Section.objects.create(project=other, name="Réunion")

        self.assertEqual(Section.objects.count(), 2)

    def test_parent_d_un_autre_projet_refuse(self):
        other = Project.objects.create(name="Q")
        parent = Section.objects.create(project=other, name="A")
        section = Section(project=self.project, parent=parent, name="B")

        with self.assertRaises(ValidationError):
            section.clean()

    def test_affichage_du_chemin(self):
        section = section_for(self.project, ["Réunion", "Préparation"])

        assert section is not None
        self.assertEqual(label(section), "Réunion › Préparation")
        self.assertEqual(str(section), "Réunion › Préparation")

    def test_supprimer_un_niveau_supprime_ses_descendants(self):
        section_for(self.project, ["A", "B", "C"])

        Section.objects.get(name="A").delete()

        self.assertFalse(Section.objects.exists())

    def test_supprimer_le_projet_supprime_ses_sections(self):
        section_for(self.project, ["A", "B"])

        self.project.delete()

        self.assertFalse(Section.objects.exists())

    def test_section_protegee_par_une_note_part(self):
        section = section_for(self.project, ["A"])
        note = Note.objects.create(date="2025-11-24")
        NotePart.objects.create(note=note, project=self.project, section=section)

        with self.assertRaises(Exception) as caught:
            section.delete()

        self.assertEqual(type(caught.exception).__name__, "ProtectedError")


class TreeTests(TestCase):
    def setUp(self):
        self.project = Project.objects.create(name="P")
        self.leaf = section_for(self.project, ["A", "B", "C"])
        section_for(self.project, ["A", "D"])
        section_for(self.project, ["E"])

    def test_ancetres_de_la_racine_a_la_section(self):
        assert self.leaf is not None
        self.assertEqual(
            [section.name for section in ancestors_and_self(self.leaf)], ["A", "B", "C"]
        )

    def test_sous_arbre_inclut_la_section_et_ses_descendants(self):
        a = Section.objects.get(name="A")

        self.assertEqual(
            sorted(section.name for section in subtree(a)), ["A", "B", "C", "D"]
        )

    def test_sous_arbre_d_une_feuille(self):
        assert self.leaf is not None
        self.assertEqual([section.name for section in subtree(self.leaf)], ["C"])


class TreeSetsTests(TestCase):
    def setUp(self):
        self.project = Project.objects.create(name="P")
        self.leaf = section_for(self.project, ["A", "B", "C"])
        self.d = section_for(self.project, ["A", "D"])
        self.e = section_for(self.project, ["E"])
        self.a = Section.objects.get(name="A")
        self.b = Section.objects.get(name="B")

    def test_avec_ancetres(self):
        assert self.leaf is not None
        self.assertEqual(
            with_ancestors([self.leaf.pk]), {self.a.pk, self.b.pk, self.leaf.pk}
        )

    def test_avec_ancetres_sans_doublon(self):
        assert self.leaf is not None and self.d is not None
        self.assertEqual(
            with_ancestors([self.leaf.pk, self.d.pk]),
            {self.a.pk, self.b.pk, self.leaf.pk, self.d.pk},
        )

    def test_avec_descendants(self):
        assert self.leaf is not None and self.d is not None
        self.assertEqual(
            with_descendants([self.a.pk]),
            {self.a.pk, self.b.pk, self.leaf.pk, self.d.pk},
        )

    def test_avec_descendants_d_une_feuille(self):
        assert self.leaf is not None
        self.assertEqual(with_descendants([self.leaf.pk]), {self.leaf.pk})

    def test_etiquettes_avec_le_projet(self):
        assert self.leaf is not None and self.e is not None
        labels = path_labels()

        self.assertEqual(labels[self.leaf.pk], "P › A › B › C")
        self.assertEqual(labels[self.e.pk], "P › E")

    def test_etiquettes_en_deux_requetes(self):
        with self.assertNumQueries(1):
            path_labels()


class ForgetUnusedTests(TestCase):
    def setUp(self):
        self.project = Project.objects.create(name="P")
        self.note = Note.objects.create(date="2025-11-24")

    def part(self, *names: str) -> NotePart:
        return NotePart.objects.create(
            note=self.note,
            project=self.project,
            section=section_for(self.project, list(names)),
        )

    def test_section_inutilisee_oubliee(self):
        section_for(self.project, ["Ancien"])

        self.assertEqual(forget_unused_sections(), 1)
        self.assertFalse(Section.objects.exists())

    def test_parent_garde_tant_qu_un_descendant_sert(self):
        self.part("A", "B", "C")
        section_for(self.project, ["A", "D"])

        forget_unused_sections()

        self.assertEqual(
            sorted(Section.objects.values_list("name", flat=True)), ["A", "B", "C"]
        )

    def test_section_utilisee_par_une_tache(self):
        section = section_for(self.project, ["A"])
        Todo.objects.create(title="T", project=self.project, section=section)

        self.assertEqual(forget_unused_sections(), 0)

    def test_section_utilisee_par_une_tache_ecartee(self):
        section = section_for(self.project, ["A"])
        Todo.objects.create(
            title="T",
            project=self.project,
            section=section,
            created_from_note=True,
            note_state=Todo.NoteState.DISMISSED,
        )

        self.assertEqual(forget_unused_sections(), 0)

    def test_rien_a_oublier(self):
        self.part("A")

        self.assertEqual(forget_unused_sections(), 0)


class SectionChoiceFieldTests(TestCase):
    def test_etiquette_projet_et_chemin(self):
        project = Project.objects.create(name="ASTERICS")
        section = section_for(project, ["Réunion", "Préparation"])
        field = SectionChoiceField(queryset=Section.objects.all())

        assert section is not None
        self.assertEqual(
            field.label_from_instance(section), "ASTERICS › Réunion › Préparation"
        )

    def test_nombre_de_requetes_constant(self):
        project = Project.objects.create(name="P")
        for index in range(12):
            section_for(project, [f"N{index}", "Sous"])
        field = SectionChoiceField(queryset=Section.objects.all())

        with self.assertNumQueries(2):
            labels = [label for _, label in field.choices]

        self.assertEqual(len(labels), 25)


class SubjectsToSectionsMigrationTests(TransactionTestCase):
    """La migration des sujets en sections, sur des données d'avant (#295)."""

    before = [
        ("core", "0005_clear_project_descriptions"),
        ("note_taking", "0034_notepart_heading_path"),
        ("todolist", "0017_todo_note_state"),
    ]
    after = [
        ("core", "0007_delete_subject"),
        ("note_taking", "0035_notepart_section"),
        ("todolist", "0018_todo_section"),
    ]

    def migrate(self, targets):
        executor = MigrationExecutor(connection)
        executor.migrate(targets)
        return executor.loader.project_state(targets).apps

    def setUp(self):
        old = self.migrate(self.before)
        Project = old.get_model("core", "Project")
        Subject = old.get_model("core", "Subject")
        NotePart = old.get_model("note_taking", "NotePart")
        Note = old.get_model("note_taking", "Note")
        Todo = old.get_model("todolist", "Todo")
        alpha = Project.objects.create(name="Alpha", color="teal")
        beta = Project.objects.create(name="Beta", color="pink")
        meeting = Subject.objects.create(name="Réunion")
        lower = Subject.objects.create(name="réunion")
        Subject.objects.create(name="Inutilisé")
        note = Note.objects.create(date="2025-11-24", body="x")
        make = NotePart.objects.create
        self.part_alpha = make(note=note, project=alpha, subject=meeting).pk
        self.part_alpha_case = make(note=note, project=alpha, subject=lower).pk
        self.part_beta = make(note=note, project=beta, subject=meeting).pk
        self.part_none = make(note=note, project=alpha, subject=None).pk
        self.todo_alpha = Todo.objects.create(
            title="T", project=alpha, subject=meeting
        ).pk
        self.todo_none = Todo.objects.create(title="U", project=alpha).pk
        self.alpha, self.beta = alpha.pk, beta.pk

    def tearDown(self):
        executor = MigrationExecutor(connection)
        executor.migrate(executor.loader.graph.leaf_nodes())

    def test_sujets_devenus_sections_sous_leur_projet(self):
        new = self.migrate(self.after)
        Section = new.get_model("core", "Section")
        NotePart = new.get_model("note_taking", "NotePart")
        Todo = new.get_model("todolist", "Todo")

        part_alpha = NotePart.objects.get(pk=self.part_alpha).section
        part_alpha_case = NotePart.objects.get(pk=self.part_alpha_case).section
        part_beta = NotePart.objects.get(pk=self.part_beta).section
        todo_alpha = Todo.objects.get(pk=self.todo_alpha).section

        # Même projet, même sujet (casse ignorée), notes et tâches : une section.
        self.assertEqual(part_alpha, part_alpha_case)
        self.assertEqual(part_alpha, todo_alpha)
        self.assertEqual(
            (part_alpha.project_id, part_alpha.name), (self.alpha, "Réunion")
        )
        # Autre projet : autre section, de même nom.
        self.assertNotEqual(part_alpha, part_beta)
        self.assertEqual((part_beta.project_id, part_beta.name), (self.beta, "Réunion"))
        # Sans sujet, sans section ; le sujet inutilisé ne donne rien.
        self.assertIsNone(NotePart.objects.get(pk=self.part_none).section)
        self.assertIsNone(Todo.objects.get(pk=self.todo_none).section)
        self.assertEqual(Section.objects.count(), 2)
        self.assertIsNone(part_alpha.parent_id)

    def test_retour_en_arriere(self):
        self.migrate(self.after)

        old = self.migrate(self.before)

        Subject = old.get_model("core", "Subject")
        NotePart = old.get_model("note_taking", "NotePart")
        self.assertEqual(
            NotePart.objects.get(pk=self.part_alpha).subject.name, "Réunion"
        )
        self.assertEqual(
            NotePart.objects.get(pk=self.part_alpha).subject_id,
            NotePart.objects.get(pk=self.part_beta).subject_id,
        )
        self.assertIsNone(NotePart.objects.get(pk=self.part_none).subject)
        self.assertEqual(Subject.objects.filter(name="Inutilisé").count(), 0)
