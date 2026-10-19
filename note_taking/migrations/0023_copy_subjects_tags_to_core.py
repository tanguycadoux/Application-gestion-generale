"""Copie les sujets et les tags dans core.Subject et core.Tag (#20).

- Sujets : chaînes de NotePart.subject (les vides sont ignorées).
- Tags : listes JSON de NotePart.tags et modèle todolist.Tag, fusionnés
  par nom (les noms vides sont ignorés).

Chaque note part et chaque TODO est rattachée, via les champs temporaires
subject_ref et tags_ref, aux objets de même nom.
"""

from django.db import migrations


def copy_subjects_and_tags(apps, schema_editor):
    Subject = apps.get_model("core", "Subject")
    Tag = apps.get_model("core", "Tag")
    NotePart = apps.get_model("note_taking", "NotePart")
    Todo = apps.get_model("todolist", "Todo")

    subjects = {}
    tags = {}

    def subject(name):
        if name not in subjects:
            subjects[name] = Subject.objects.create(name=name)
        return subjects[name]

    def tag(name):
        if name not in tags:
            tags[name] = Tag.objects.create(name=name)
        return tags[name]

    for part in NotePart.objects.order_by("pk"):
        if part.subject:
            part.subject_ref = subject(part.subject)
            part.save(update_fields=["subject_ref"])
        part.tags_ref.set([tag(name) for name in part.tags or [] if name])

    for todo in Todo.objects.prefetch_related("tags").order_by("pk"):
        todo.tags_ref.set([tag(old.name) for old in todo.tags.all() if old.name])


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0002_subject_tag"),
        ("note_taking", "0022_notepart_subject_ref_notepart_tags_ref"),
        ("todolist", "0006_todo_tags_ref"),
    ]

    operations = [
        migrations.RunPython(copy_subjects_and_tags, migrations.RunPython.noop),
    ]
