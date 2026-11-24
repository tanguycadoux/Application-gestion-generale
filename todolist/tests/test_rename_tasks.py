"""Renommer un niveau de chemin : les tâches issues des notes suivent (#299).

Le chemin d'une tâche est fait des titres de sa section : quand un titre change, son
identité (#240) change. Les tâches gardent leur fiche (avancement, échéance, parent,
état) et leur chemin suit.
"""

from unittest import expectedFailure

from django.test import TestCase

from core.models import Project, Section
from core.sections import label, levels
from note_taking.exceptions import NoteRenameError
from note_taking.models import Note
from note_taking.renaming import find_occurrences, rename_titles
from note_taking.services import process_passages
from todolist.models import Task
from todolist.services import placed_by_note, renamed_identities


class RenameTasksTestCase(TestCase):
    def setUp(self):
        self.project = Project.objects.create(name="P")

    def note(self, body: str, day: str = "2025-11-24") -> Note:
        note = Note.objects.create(date=day, body=body)
        process_passages(note)
        return note

    def rename(self, levels_: list[str], name: str, only: int | None = None) -> None:
        keys = [o.key for o in find_occurrences(self.project, levels_)]
        rename_titles(
            self.project, levels_, name, keys if only is None else keys[only : only + 1]
        )

    def paths(self) -> list[tuple[str, str]]:
        return sorted(Task.objects.values_list("title", "note_path"))


class TasksFollowTests(RenameTasksTestCase):
    def test_la_tache_garde_sa_fiche_et_change_de_chemin(self):
        self.note("# P\n## Réunion\n- [ ] Relire")
        task = Task.objects.get()
        Task.objects.filter(pk=task.pk).update(
            progress=40, note_state=Task.NoteState.REVIEWED
        )

        self.rename(["Réunion"], "Rencontre")

        task.refresh_from_db()
        self.assertEqual(
            (task.note_path, task.progress, task.note_state),
            ("P › Rencontre", 40, Task.NoteState.REVIEWED),
        )
        self.assertEqual(Task.objects.count(), 1)

    def test_aucune_tache_perd_sa_ligne(self):
        self.note("# P\n## Réunion\n- [ ] A\n### Suite\n- [ ] B")
        Task.objects.update(note_state=Task.NoteState.REVIEWED)

        self.rename(["Réunion"], "Rencontre")

        self.assertEqual(
            set(Task.objects.values_list("note_state", flat=True)),
            {Task.NoteState.REVIEWED},
        )
        self.assertEqual(
            self.paths(), [("A", "P › Rencontre"), ("B", "P › Rencontre › Suite")]
        )

    def test_sous_taches_et_parents(self):
        self.note("# P\n## Réunion\n- [ ] A\n  - [ ] B")
        a, b = Task.objects.order_by("pk")
        self.assertEqual(b.parent, a)

        self.rename(["Réunion"], "Rencontre")

        a.refresh_from_db()
        b.refresh_from_db()
        self.assertEqual(
            (a.note_path, b.note_path, b.parent_id),
            ("P › Rencontre", "P › Rencontre › A", a.pk),
        )

    def test_branche_todo(self):
        self.note("# P\n## Réunion\n::: {.metadata}\ntodo: true\n:::\n- A")

        self.rename(["Réunion"], "Rencontre")

        self.assertEqual(self.paths(), [("A", "P › Rencontre")])

    def test_niveau_du_milieu_renomme(self):
        self.note("# P\n## A\n### B\n#### C\n- [ ] Tâche")

        self.rename(["A", "B"], "X")

        self.assertEqual(self.paths(), [("Tâche", "P › A › X › C")])

    def test_titre_au_niveau_saute(self):
        self.note("# P\n### Réunion\n- [ ] A")

        self.rename(["Réunion"], "Rencontre")

        self.assertEqual(self.paths(), [("A", "P › Rencontre")])

    def test_taches_de_plusieurs_notes(self):
        self.note("# P\n## Réunion\n- [ ] A", day="2025-11-24")
        self.note("# P\n## Réunion\n- [ ] A", day="2025-11-25")

        self.rename(["Réunion"], "Rencontre")

        self.assertEqual(Task.objects.count(), 2)
        self.assertEqual({path for _, path in self.paths()}, {"P › Rencontre"})

    def test_seule_la_note_choisie(self):
        self.note("# P\n## Réunion\n- [ ] A", day="2025-11-24")
        self.note("# P\n## Réunion\n- [ ] A", day="2025-11-25")

        self.rename(["Réunion"], "Rencontre", only=1)

        by_date = {
            task.note_date.isoformat(): task.note_path for task in Task.objects.all()
        }
        self.assertEqual(
            by_date, {"2025-11-24": "P › Réunion", "2025-11-25": "P › Rencontre"}
        )

    def test_tache_ecartee_suit_aussi(self):
        self.note("# P\n## Réunion\n- [ ] A")
        Task.objects.update(note_state=Task.NoteState.DISMISSED)

        self.rename(["Réunion"], "Rencontre")

        task = Task.all_objects.get()
        self.assertEqual(
            (task.note_path, task.note_state), ("P › Rencontre", "dismissed")
        )

    def test_tache_saisie_a_la_main_non_touchee(self):
        self.note("# P\n## Réunion\n- [ ] A")
        manual = Task.objects.create(title="À la main", project=self.project)

        self.rename(["Réunion"], "Rencontre")

        manual.refresh_from_db()
        self.assertEqual(manual.note_path, "")

    def test_la_note_est_recalculee_avec_le_nouveau_nom(self):
        note = self.note("# P\n## Réunion\n- [ ] A")

        self.rename(["Réunion"], "Rencontre")

        part = note.passages.get()
        assert part.section is not None
        self.assertEqual(levels(part.section), ["Rencontre"])


class RefusedTests(RenameTasksTestCase):
    def test_nom_deja_ecrit_dans_la_note_refuse(self):
        """Deux tâches de même texte, sous deux titres : renommer l'un comme l'autre
        les confondrait en une seule tâche (même chemin, même texte, #240)."""
        self.note("# P\n## A\n- [ ] T\n## B\n- [ ] T")
        keys = [o.key for o in find_occurrences(self.project, ["A"])]

        with self.assertRaisesMessage(
            NoteRenameError, "confondrait deux tâches « T » sous le même chemin"
        ):
            rename_titles(self.project, ["A"], "B", keys)

        self.assertEqual(self.paths(), [("T", "P › A"), ("T", "P › B")])

    def test_titres_du_meme_nom_avec_des_taches_renommes(self):
        """Deux titres qui ne diffèrent que par la casse sont deux passages (#387) ;
        les renommer pareil ne les fusionne pas : leurs tâches les suivent."""
        self.note("# P\n## réunion\n- [ ] A\n## Réunion\n- [ ] B")
        keys = [o.key for o in find_occurrences(self.project, ["Réunion"])]

        rename_titles(self.project, ["Réunion"], "RÉUNION", keys)

        self.assertEqual(
            Note.objects.get().body, "# P\n## RÉUNION\n- [ ] A\n## RÉUNION\n- [ ] B"
        )
        self.assertEqual(self.paths(), [("A", "P › RÉUNION"), ("B", "P › RÉUNION")])

    def test_fusion_de_parties_sans_tache_permise(self):
        self.note("# P\n## réunion\nx\n## Réunion\ny")
        keys = [o.key for o in find_occurrences(self.project, ["Réunion"])]

        rename_titles(self.project, ["Réunion"], "RÉUNION", keys)

        self.assertEqual(Note.objects.get().body, "# P\n## RÉUNION\nx\n## RÉUNION\ny")
        self.assertEqual(Section.objects.count(), 1)


class RenamedIdentitiesTests(RenameTasksTestCase):
    def test_lignes_dont_le_chemin_change(self):
        old = "# P\n## A\n- [ ] T\n  - [ ] U"
        new = "# P\n## B\n- [ ] T\n  - [ ] U"

        moves = renamed_identities("2025-11-24", old, new)  # type: ignore[arg-type]

        self.assertEqual(
            [((a.path, a.text), (b.path, b.text)) for a, b in moves],
            [
                (("P › A", "T"), ("P › B", "T")),
                (("P › A › T", "U"), ("P › B › T", "U")),
            ],
        )

    def test_aucune_ligne_ne_change(self):
        body = "# P\n## A\n- [ ] T"

        self.assertEqual(renamed_identities("2025-11-24", body, body), [])  # type: ignore[arg-type]


class PartialRenameTests(RenameTasksTestCase):
    """Un renommage partiel : les tâches des titres réécrits passent au nouveau niveau,
    les autres restent (#443)."""

    def places(self) -> list[tuple[str, str]]:
        return sorted(
            (task.title, f"{task.project} › {label(task.section)}")
            for task in Task.objects.exclude(section=None)
        )

    def start(self, under: str = "") -> None:
        self.note(f"# P\n## A\n{under}- [ ] Un")
        self.note(f"# P\n## A\n{under}- [ ] Deux", day="2025-11-25")
        Task.objects.update(note_state=Task.NoteState.REVIEWED)

    @expectedFailure
    def test_seules_les_taches_des_titres_reecrits_suivent(self):
        self.start()

        self.rename(["A"], "B", only=1)

        self.assertEqual(self.places(), [("Deux", "P › B"), ("Un", "P › A")])

    @expectedFailure
    def test_sous_niveaux_compris(self):
        self.start("### C\n")

        self.rename(["A"], "B", only=1)

        self.assertEqual(self.places(), [("Deux", "P › B › C"), ("Un", "P › A › C")])

    @expectedFailure
    def test_tache_ecartee_aussi(self):
        self.start()
        Task.objects.filter(title="Deux").update(note_state=Task.NoteState.DISMISSED)

        self.rename(["A"], "B", only=1)

        task = Task.all_objects.get(title="Deux")
        self.assertEqual(str(task.section), "B")

    @expectedFailure
    def test_vers_un_niveau_existant(self):
        """Une réunion partielle (#373)."""
        self.start()
        self.note("# P\n## B\n- [ ] Trois", day="2025-11-26")

        self.rename(["A"], "B", only=1)

        self.assertEqual(
            self.places(), [("Deux", "P › B"), ("Trois", "P › B"), ("Un", "P › A")]
        )
        self.assertEqual(Section.objects.filter(name="B").count(), 1)

    def test_niveau_choisi_a_la_main_garde(self):
        self.start()
        other = Section.objects.create(project=self.project, name="Ailleurs")
        Task.objects.filter(title="Deux").update(section=other)

        self.rename(["A"], "B", only=1)

        self.assertEqual(self.places(), [("Deux", "P › Ailleurs"), ("Un", "P › A")])

    def test_projet_choisi_a_la_main_garde(self):
        self.start()
        other = Project.objects.create(name="Q")
        Task.objects.filter(title="Deux").update(project=other, section=None)

        self.rename(["A"], "B", only=1)

        self.assertEqual(Task.objects.get(title="Deux").project, other)
        self.assertEqual(self.places(), [("Un", "P › A")])

    def test_tache_saisie_a_la_main_reste(self):
        self.start()
        Task.objects.create(
            title="Main", project=self.project, section=Section.objects.get(name="A")
        )

        self.rename(["A"], "B", only=1)

        self.assertIn(("Main", "P › A"), self.places())

    @expectedFailure
    def test_suit_encore_les_changements_suivants(self):
        """Son niveau est celui de sa ligne : `placed_by_note` le reconnaît."""
        self.start()

        self.rename(["A"], "B", only=1)

        self.assertTrue(all(placed_by_note(task) for task in Task.objects.all()))
