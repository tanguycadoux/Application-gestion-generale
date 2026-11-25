"""La migration des note parts aux passages (#387) : l'index dérivé est recalculé
par la migration elle-même, et les tâches issues des notes sont gardées telles
quelles (mêmes fiches, même identité)."""

from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase

from note_taking.search import search_passages
from note_taking.search_query import parse_query

BODY = "intro\n# A\n- [ ] écrire\n# B\nmot\n# A\nsuite"


class PassageMigrationTests(TransactionTestCase):
    before = [
        ("note_taking", "0041_saved_search_filters"),
        ("todolist", "0020_rename_todo_task"),
    ]
    after = [("note_taking", "0042_passages")]

    @property
    def migrated(self):
        """`after`, les tâches d'abord à leur dernier schéma : le recalcul de la
        migration est celui de l'application, il en crée avec le code
        d'aujourd'hui (un champ ajouté depuis, comme `no_due_date`, #384)."""
        graph = MigrationExecutor(connection).loader.graph
        return [*graph.leaf_nodes("todolist"), *self.after]

    def migrate(self, targets):
        executor = MigrationExecutor(connection)
        # Une cible après l'autre, dans l'ordre donné : en un seul plan, le recalcul
        # de `0042_passages` ne voit pas les colonnes ajoutées juste avant.
        for target in targets:
            executor.migrate([target])
            executor.loader.build_graph()
        return executor.loader.project_state(targets).apps

    def setUp(self):
        old = self.migrate(self.before)
        Project = old.get_model("core", "Project")
        Note = old.get_model("note_taking", "Note")
        NotePart = old.get_model("note_taking", "NotePart")
        Task = old.get_model("todolist", "Task")
        project = Project.objects.create(name="A")
        note = Note.objects.create(date="2026-11-22", body=BODY)
        NotePart.objects.create(
            note=note, project=project, content="- [ ] écrire", heading_path="A"
        )
        self.task = Task.objects.create(
            title="écrire",
            project=project,
            created_from_note=True,
            note_part_date="2026-11-22",
            note_path="A",
            note_part_text="écrire",
            note_state="reviewed",
        ).pk

    def tearDown(self):
        executor = MigrationExecutor(connection)
        executor.migrate(executor.loader.graph.leaf_nodes())

    def test_passages_recalcules_et_taches_gardees(self):
        new = self.migrate(self.migrated)
        Passage = new.get_model("note_taking", "Passage")
        Task = new.get_model("todolist", "Task")

        self.assertEqual(
            list(
                Passage.objects.order_by("position").values_list(
                    "position", "project__name", "heading_id"
                )
            ),
            [(0, None, ""), (1, "A", "a"), (2, "B", "b"), (3, "A", "a-1")],
        )
        task = Task.objects.get(pk=self.task)
        self.assertEqual(
            (task.note_date.isoformat(), task.note_path, task.note_line_text),
            ("2026-11-22", "A", "écrire"),
        )
        self.assertEqual(task.note_state, "reviewed")
        self.assertEqual(Task.objects.count(), 1)
        tables = connection.introspection.table_names()
        self.assertNotIn("note_taking_notepart", tables)
        self.assertNotIn("note_part_search", tables)

    def test_index_de_recherche_rempli(self):
        # La recherche est celle d'aujourd'hui : elle lit les colonnes ajoutées aux notes
        # depuis (`updated_by`, #468).
        graph = MigrationExecutor(connection).loader.graph
        self.migrate([*self.migrated, *graph.leaf_nodes("note_taking")])

        found = search_passages(parse_query("intro")) or []

        self.assertEqual([passage.content for passage in found], ["intro"])
