"""Renommer un niveau de chemin : les tâches issues des notes suivent (#299).

Le chemin d'une tâche est fait des titres de sa section : quand un titre change, son
identité (#240) change. Les tâches gardent leur fiche (avancement, échéance, parent,
état) et leur chemin suit.
"""

from django.test import TestCase

from core.models import Project, Section
from core.sections import levels
from note_taking.exceptions import NoteRenameError
from note_taking.models import Note
from note_taking.renaming import find_occurrences, rename_titles
from note_taking.services import process_note_parts
from todolist.models import Todo
from todolist.services import renamed_identities


class RenameTasksTestCase(TestCase):
    def setUp(self):
        self.project = Project.objects.create(name="P")

    def note(self, body: str, day: str = "2025-11-24") -> Note:
        note = Note.objects.create(date=day, body=body)
        process_note_parts(note)
        return note

    def rename(self, levels_: list[str], name: str, only: int | None = None) -> None:
        keys = [o.key for o in find_occurrences(self.project, levels_)]
        rename_titles(
            self.project, levels_, name, keys if only is None else keys[only : only + 1]
        )

    def paths(self) -> list[tuple[str, str]]:
        return sorted(Todo.objects.values_list("title", "note_path"))


class TasksFollowTests(RenameTasksTestCase):
    def test_la_tache_garde_sa_fiche_et_change_de_chemin(self):
        self.note("# P\n## Réunion\n- [ ] Relire")
        todo = Todo.objects.get()
        Todo.objects.filter(pk=todo.pk).update(
            progress=40, note_state=Todo.NoteState.REVIEWED
        )

        self.rename(["Réunion"], "Rencontre")

        todo.refresh_from_db()
        self.assertEqual(
            (todo.note_path, todo.progress, todo.note_state),
            ("P › Rencontre", 40, Todo.NoteState.REVIEWED),
        )
        self.assertEqual(Todo.objects.count(), 1)

    def test_aucune_tache_perd_sa_ligne(self):
        self.note("# P\n## Réunion\n- [ ] A\n### Suite\n- [ ] B")
        Todo.objects.update(note_state=Todo.NoteState.REVIEWED)

        self.rename(["Réunion"], "Rencontre")

        self.assertEqual(
            set(Todo.objects.values_list("note_state", flat=True)),
            {Todo.NoteState.REVIEWED},
        )
        self.assertEqual(
            self.paths(), [("A", "P › Rencontre"), ("B", "P › Rencontre › Suite")]
        )

    def test_sous_taches_et_parents(self):
        self.note("# P\n## Réunion\n- [ ] A\n  - [ ] B")
        a, b = Todo.objects.order_by("pk")
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

        self.assertEqual(Todo.objects.count(), 2)
        self.assertEqual({path for _, path in self.paths()}, {"P › Rencontre"})

    def test_seule_la_note_choisie(self):
        self.note("# P\n## Réunion\n- [ ] A", day="2025-11-24")
        self.note("# P\n## Réunion\n- [ ] A", day="2025-11-25")

        self.rename(["Réunion"], "Rencontre", only=1)

        by_date = {
            todo.note_part_date.isoformat(): todo.note_path
            for todo in Todo.objects.all()
        }
        self.assertEqual(
            by_date, {"2025-11-24": "P › Réunion", "2025-11-25": "P › Rencontre"}
        )

    def test_tache_ecartee_suit_aussi(self):
        self.note("# P\n## Réunion\n- [ ] A")
        Todo.objects.update(note_state=Todo.NoteState.DISMISSED)

        self.rename(["Réunion"], "Rencontre")

        todo = Todo.all_objects.get()
        self.assertEqual(
            (todo.note_path, todo.note_state), ("P › Rencontre", "dismissed")
        )

    def test_tache_saisie_a_la_main_non_touchee(self):
        self.note("# P\n## Réunion\n- [ ] A")
        manual = Todo.objects.create(title="À la main", project=self.project)

        self.rename(["Réunion"], "Rencontre")

        manual.refresh_from_db()
        self.assertEqual(manual.note_path, "")

    def test_la_note_est_recalculee_avec_le_nouveau_nom(self):
        note = self.note("# P\n## Réunion\n- [ ] A")

        self.rename(["Réunion"], "Rencontre")

        part = note.parts.get()
        assert part.section is not None
        self.assertEqual(levels(part.section), ["Rencontre"])


class RefusedTests(RenameTasksTestCase):
    def test_nom_deja_ecrit_dans_la_note_refuse(self):
        """Deux tâches de même texte, sous deux titres : renommer l'un comme l'autre
        les confondrait. Les parties de la note fusionnent, les lignes ne se
        retrouvent plus."""
        self.note("# P\n## A\n- [ ] T\n## B\n- [ ] T")
        keys = [o.key for o in find_occurrences(self.project, ["A"])]

        with self.assertRaisesMessage(NoteRenameError, "fusionnerait"):
            rename_titles(self.project, ["A"], "B", keys)

        self.assertEqual(self.paths(), [("T", "P › A"), ("T", "P › B")])

    def test_fusion_de_parties_avec_des_taches_refusee(self):
        """Deux titres qui ne diffèrent que par la casse sont deux parties ; les
        renommer pareil les fusionnerait, et les lignes ne se retrouveraient plus."""
        self.note("# P\n## réunion\n- [ ] A\n## Réunion\n- [ ] B")
        keys = [o.key for o in find_occurrences(self.project, ["Réunion"])]

        with self.assertRaisesMessage(NoteRenameError, "fusionnerait"):
            rename_titles(self.project, ["Réunion"], "RÉUNION", keys)

        self.assertEqual(
            Note.objects.get().body, "# P\n## réunion\n- [ ] A\n## Réunion\n- [ ] B"
        )
        self.assertEqual(self.paths(), [("A", "P › réunion"), ("B", "P › Réunion")])

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
