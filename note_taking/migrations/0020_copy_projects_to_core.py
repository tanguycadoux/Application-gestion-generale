"""Copie les projets des notes et des TODO dans core.Project (#19).

Les projets sont fusionnés par nom. Chaque note part et chaque TODO est
rattachée, via le champ temporaire core_project, au projet de même nom.
"""

from django.db import migrations


def copy_projects(apps, schema_editor):
    CoreProject = apps.get_model("core", "Project")
    NoteProject = apps.get_model("note_taking", "Project")
    TodoProject = apps.get_model("todolist", "Project")
    NotePart = apps.get_model("note_taking", "NotePart")
    Todo = apps.get_model("todolist", "Todo")

    projects = {}

    for old in NoteProject.objects.order_by("pk"):
        projects[old.name] = CoreProject.objects.create(
            name=old.name, description=old.description or ""
        )

    # Les projets de todolist (noms non uniques) : on garde la date de
    # création la plus ancienne et la première description non vide.
    dated = set()
    for old in TodoProject.objects.order_by("created_at", "pk"):
        project = projects.get(old.name)
        if project is None:
            project = projects[old.name] = CoreProject.objects.create(
                name=old.name, description=old.description, created_at=old.created_at
            )
        else:
            if old.name not in dated:
                project.created_at = old.created_at
            if not project.description and old.description:
                project.description = old.description
            project.save()
        dated.add(old.name)

    for part in NotePart.objects.select_related("project"):
        part.core_project = projects[part.project.name]
        part.save(update_fields=["core_project"])

    for todo in Todo.objects.exclude(project=None).select_related("project"):
        todo.core_project = projects[todo.project.name]
        todo.save(update_fields=["core_project"])


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0001_initial"),
        ("note_taking", "0019_notepart_core_project"),
        ("todolist", "0004_todo_core_project"),
    ]

    operations = [
        migrations.RunPython(copy_projects, migrations.RunPython.noop),
    ]
