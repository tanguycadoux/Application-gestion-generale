"""La migration `Todo` → `Task` (#194) garde les tâches, leurs tags et leur
parent ; la table et la table des tags suivent le nouveau nom."""

from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase


class RenameTodoToTaskMigrationTests(TransactionTestCase):
    before = [("todolist", "0019_alter_todo_section")]
    after = [("todolist", "0020_rename_todo_task")]

    def migrate(self, targets):
        executor = MigrationExecutor(connection)
        executor.migrate(targets)
        return executor.loader.project_state(targets).apps

    def setUp(self):
        old = self.migrate(self.before)
        Project = old.get_model("core", "Project")
        Tag = old.get_model("core", "Tag")
        Todo = old.get_model("todolist", "Todo")
        project = Project.objects.create(name="P")
        parent = Todo.objects.create(title="Parent", project=project)
        child = Todo.objects.create(title="Enfant", project=project, parent=parent)
        child.tags.add(Tag.objects.create(name="urgent"))
        self.parent, self.child = parent.pk, child.pk

    def tearDown(self):
        executor = MigrationExecutor(connection)
        executor.migrate(executor.loader.graph.leaf_nodes())

    def test_taches_tags_et_parent_gardes(self):
        new = self.migrate(self.after)
        Task = new.get_model("todolist", "Task")
        Project = new.get_model("core", "Project")

        child = Task.objects.get(pk=self.child)
        self.assertEqual(child.title, "Enfant")
        self.assertEqual(child.parent_id, self.parent)
        self.assertEqual([tag.name for tag in child.tags.all()], ["urgent"])
        self.assertEqual(Project.objects.get(name="P").tasks.count(), 2)
        tables = connection.introspection.table_names()
        self.assertIn("todolist_task", tables)
        self.assertIn("todolist_task_tags", tables)
        self.assertNotIn("todolist_todo", tables)
        self.assertNotIn("todolist_todo_tags", tables)
