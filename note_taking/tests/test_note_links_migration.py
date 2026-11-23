"""La migration des liens entre notes (#207) les calcule pour les passages
existants, sans `reprocess_notes`."""

from datetime import date

from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase


class NoteLinksMigrationTests(TransactionTestCase):
    before = [("note_taking", "0043_saved_search_no_project")]
    after = [("note_taking", "0044_passagenotelink")]

    def migrate(self, targets):
        executor = MigrationExecutor(connection)
        executor.migrate(targets)
        executor.loader.build_graph()
        return executor.loader.project_state(targets).apps

    def tearDown(self):
        executor = MigrationExecutor(connection)
        executor.migrate(executor.loader.graph.leaf_nodes())

    def test_liens_des_passages_existants(self):
        old = self.migrate(self.before)
        Note = old.get_model("note_taking", "Note")
        Passage = old.get_model("note_taking", "Passage")
        note = Note.objects.create(date="2026-03-14", body="")
        Passage.objects.create(
            note=note,
            position=0,
            content="[a](2026-03-12.qmd) `[b](2026-03-11.qmd)`\n"
            "[c](2026-03-12.qmd#x) [d](2026-03-12.qmd)",
        )
        Passage.objects.create(note=note, position=1, content="sans lien")

        new = self.migrate(self.after)
        Link = new.get_model("note_taking", "PassageNoteLink")

        self.assertEqual(
            sorted(Link.objects.values_list("target_date", "anchor")),
            [(date(2026, 3, 12), ""), (date(2026, 3, 12), "x")],
        )
