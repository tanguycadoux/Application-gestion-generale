"""Commande convert_todo_sections : réécrire les sections TODO en cases (#297)."""

from datetime import date
from io import StringIO

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase

from core.models import Project
from note_taking.models import Note
from todolist.models import Todo

OLD = "# P\n## S\n### TODO\n\n- A\n  - B\n- C\n"
NEW = "# P\n## S\n- [ ] A\n  - [ ] B\n- [ ] C\n"


class ConvertTestCase(TestCase):
    def setUp(self):
        self.project = Project.objects.create(name="P")

    def note(self, body: str, day: str = "2025-11-24") -> Note:
        return Note.objects.create(date=day, body=body)

    def task(self, text: str, path: str, day: str = "2025-11-24", **fields) -> Todo:
        """Une tâche créée avant #297 : revue, identifiée par sa date, son chemin
        de titres sans `TODO` et son texte."""
        return Todo.objects.create(
            title=text,
            project=self.project,
            created_from_note=True,
            note_part_date=date.fromisoformat(day),
            note_path=path,
            note_part_text=text,
            note_state=fields.pop("note_state", Todo.NoteState.REVIEWED),
            **fields,
        )

    def run_command(self, *args) -> str:
        out = StringIO()
        call_command("convert_todo_sections", *args, stdout=out, stderr=StringIO())
        return out.getvalue()


class PreviewTests(ConvertTestCase):
    def test_apercu_sans_rien_ecrire(self):
        note = self.note(OLD)

        out = self.run_command()

        note.refresh_from_db()
        self.assertEqual(note.body, OLD)
        self.assertIn("Note du 2025-11-24 : 1 section(s) TODO", out)
        self.assertIn("ligne 5 : - A  ->  - [ ] A", out)
        self.assertIn("ligne 3 : retirée", out)
        self.assertIn("Rien n'a été modifié", out)

    def test_cases_deja_presentes_listees(self):
        self.note("# P\n- [ ] Ouverte\n- [x] Cochée\n### TODO\n- A")

        out = self.run_command()

        self.assertIn("1 case(s) vide(s) hors section TODO", out)
        self.assertIn("2025-11-24, ligne 2 : [ ] Ouverte", out)
        self.assertIn("1 case(s) cochée(s), ignorée(s)", out)
        self.assertIn("2025-11-24, ligne 3 : [x] Cochée", out)

    def test_point_a_corriger_signale_sans_erreur(self):
        self.note("# P\n### TODO\nUn paragraphe.\n- A")

        out = self.run_command()

        self.assertIn("Ligne 3", out)
        self.assertIn("point(s) à corriger à la main", out)


class ApplyTests(ConvertTestCase):
    def test_note_reecrite_et_tache_gardee(self):
        note = self.note(OLD)
        a = self.task("A", "P › S")
        b = self.task("B", "P › S › A", parent=a)
        c = self.task("C", "P › S")

        out = self.run_command("--apply")

        note.refresh_from_db()
        self.assertEqual(note.body, NEW)
        self.assertEqual(Todo.objects.count(), 3)
        for todo in (a, b, c):
            todo.refresh_from_db()
            self.assertEqual(todo.note_state, Todo.NoteState.REVIEWED)
        b.refresh_from_db()
        self.assertEqual(b.parent, a)
        self.assertIn(
            "1 note(s) réécrite(s), 0 autre(s) recalculée(s) ; 0 tâche(s)", out
        )

    def test_cases_deja_presentes_deviennent_des_taches(self):
        self.note("# P\n- [ ] Ouverte\n- [x] Cochée\n### TODO\n- A")
        self.task("A", "P")

        out = self.run_command("--apply")

        self.assertEqual(
            sorted(Todo.objects.values_list("title", flat=True)), ["A", "Ouverte"]
        )
        self.assertEqual(
            Todo.objects.get(title="Ouverte").note_state, Todo.NoteState.TO_REVIEW
        )
        self.assertIn("1 tâche(s) créée(s)", out)

    def test_notes_sans_section_inchangees(self):
        other = self.note("# P\n- texte", day="2025-11-25")
        self.note(OLD)
        self.task("A", "P › S")
        self.task("C", "P › S")

        self.run_command("--apply")

        other.refresh_from_db()
        self.assertEqual(other.body, "# P\n- texte")

    def test_fins_de_ligne_windows_conservees(self):
        note = self.note(OLD.replace("\n", "\r\n"))
        self.task("A", "P › S")
        self.task("C", "P › S")

        self.run_command("--apply")

        note.refresh_from_db()
        self.assertEqual(note.body, NEW.replace("\n", "\r\n"))

    def test_relancer_ne_change_plus_rien(self):
        self.note(OLD)
        self.task("A", "P › S")
        self.task("C", "P › S")
        self.run_command("--apply")

        out = self.run_command("--apply")

        self.assertIn("0 note(s) réécrite(s)", out)
        self.assertIn("0 tâche(s) créée(s)", out)

    def test_point_a_corriger_refuse_tout(self):
        good = self.note(OLD, day="2025-11-24")
        bad = self.note("# P\n### TODO\nUn paragraphe.", day="2025-11-25")

        with self.assertRaisesMessage(CommandError, "Rien n'a été modifié"):
            self.run_command("--apply")

        for note, body in ((good, OLD), (bad, "# P\n### TODO\nUn paragraphe.")):
            note.refresh_from_db()
            self.assertEqual(note.body, body)

    def test_tache_revue_qui_perdrait_sa_ligne_annule_tout(self):
        """Garde-fou : l'identité des tâches (#240) ne doit pas bouger."""
        note = self.note(OLD)
        self.task("A", "P › S")
        ghost = self.task("fantôme", "P › S")

        with self.assertRaisesMessage(CommandError, "perdraient leur ligne"):
            self.run_command("--apply")

        note.refresh_from_db()
        ghost.refresh_from_db()
        self.assertEqual(note.body, OLD)
        self.assertEqual(ghost.note_state, Todo.NoteState.REVIEWED)


class MovedTasksTests(ConvertTestCase):
    """Le titre `TODO` retiré, la liste passe sous le titre qui le précédait : les
    tâches déjà créées gardent leur fiche et changent de chemin."""

    BODY = "# P\n## S\n### Notes\ntexte\n### TODO\n\n- A\n#### Détail\n- B\n"

    def test_apercu_des_taches_deplacees(self):
        self.note(self.BODY)
        self.task("A", "P › S")

        out = self.run_command()

        self.assertIn("1 tâche(s) déjà créée(s) changent de chemin", out)
        self.assertIn("« A »", out)
        self.assertIn("P › S  ->  P › S › Notes", out)

    def test_taches_rangees_sous_leur_nouveau_chemin(self):
        note = self.note(self.BODY)
        a = self.task("A", "P › S", progress=40)
        b = self.task("B", "P › S › Détail")

        self.run_command("--apply")

        for todo, path in ((a, "P › S › Notes"), (b, "P › S › Notes › Détail")):
            todo.refresh_from_db()
            self.assertEqual(todo.note_path, path)
            self.assertEqual(todo.note_state, Todo.NoteState.REVIEWED)
        a.refresh_from_db()
        self.assertEqual(a.progress, 40)
        self.assertEqual(Todo.objects.count(), 2)
        note.refresh_from_db()
        self.assertEqual(
            note.body,
            "# P\n## S\n### Notes\ntexte\n\n- [ ] A\n#### Détail\n- [ ] B\n",
        )

    def test_garde_fou_apres_le_rangement(self):
        """Seule la tâche dont la ligne a vraiment disparu fait tout annuler."""
        note = self.note(self.BODY)
        self.task("A", "P › S")
        ghost = self.task("fantôme", "P › S")

        with self.assertRaisesMessage(CommandError, "perdraient leur ligne"):
            self.run_command("--apply")

        note.refresh_from_db()
        ghost.refresh_from_db()
        self.assertEqual(note.body, self.BODY)
        self.assertEqual(ghost.note_path, "P › S")
        self.assertEqual(Todo.objects.get(title="A").note_path, "P › S")


class BoxedNotesTests(ConvertTestCase):
    def test_note_a_case_vide_sans_section_recalculee(self):
        """Ses cases deviennent des tâches : la note est recalculée, pas réécrite."""
        note = self.note("# P\n- [ ] Ouverte\n- [x] Fait")

        out = self.run_command("--apply")

        note.refresh_from_db()
        self.assertEqual(note.body, "# P\n- [ ] Ouverte\n- [x] Fait")
        self.assertEqual(
            list(Todo.objects.values_list("title", flat=True)), ["Ouverte"]
        )
        self.assertIn(
            "0 note(s) réécrite(s), 1 autre(s) recalculée(s) ; 1 tâche(s)", out
        )

    def test_tache_saisie_a_la_main_non_comptee(self):
        self.note("# P\n- texte")
        Todo.objects.create(title="À la main", project=self.project)

        out = self.run_command("--apply")

        self.assertIn("0 tâche(s) créée(s)", out)
