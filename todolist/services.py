import re

from core.models import Project, Subject, Tag
from note_taking.models import NotePart

from .models import TODO_TEXT_MAX_LENGTH, Todo

# Marqueur de liste en tête de ligne, avec sa case éventuelle : « - », « * [x] »,
# « 1. », « 2) [ ] »… Seul, sans texte, il donne une ligne vide.
LIST_MARKER_REGEX = re.compile(r"^(?:[-*+]|\d+[.)])(?:\s+\[[ xX]\])?(?:\s+|$)")


def create_todo_from_dict(todo_data: dict) -> Todo:
    project, _ = Project.objects.get_or_create(name=todo_data["project"])
    subject = (
        Subject.objects.get_or_create(name=todo_data["subject"])[0]
        if todo_data.get("subject")
        else None
    )

    todo, created = Todo.objects.get_or_create(
        created_from_note=True,
        note_part_date=todo_data["date"],
        note_part_text=todo_data["content"],
        defaults={
            "title": todo_data["content"],
            "project": project,
            "subject": subject,
            "due_date": todo_data["date"],
        },
    )

    if created:
        tag_names = todo_data.get("tags", [])

        if tag_names:
            tags = [Tag.objects.get_or_create(name=name)[0] for name in tag_names]
            todo.tags.add(*tags)
    return todo


def todo_text(line: str) -> str:
    """Texte d'une ligne de TODO, sans marqueur de liste ni case (#222).

    Marqueurs Markdown : `-`, `*`, `+`, `1.`, `1)`, suivis d'une case `[ ]` ou
    `[x]` éventuelle ; une case cochée ne termine pas la tâche. Le texte est
    borné à la longueur des champs.
    """
    text = LIST_MARKER_REGEX.sub("", line.strip(), count=1)
    return text.strip()[:TODO_TEXT_MAX_LENGTH]


def create_todos_from_note_part(note_part: NotePart):
    """Une tâche par ligne d'une note part marquée TODO."""
    part_tags = [tag.name for tag in note_part.tags.all()]
    subject = note_part.subject.name if note_part.subject else None

    if "TODO" in part_tags:
        tags = [tag for tag in part_tags if tag != "TODO"]

        for raw_line in note_part.content.split("\n"):
            line = todo_text(raw_line)
            if not line:
                continue

            todo_data = {
                "date": note_part.note.date,
                "project": note_part.project.name,
                "content": line,
                "subject": subject,
                "tags": tags,
            }
            create_todo_from_dict(todo_data)
