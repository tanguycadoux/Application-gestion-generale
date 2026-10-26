import re
from dataclasses import dataclass

from core.models import Project, Subject, Tag
from note_taking.models import NotePart
from note_taking.qmd.lists import CODE_INDENT, LIST_ITEM_REGEX, text_column
from note_taking.qmd.parser import HEADING_SEPARATOR

from .models import TODO_TEXT_MAX_LENGTH, Todo

# Marqueur de liste en tête de ligne, avec sa case éventuelle : « - », « * [x] »,
# « 1. », « 2) [ ] »… Seul, sans texte, il donne une ligne vide.
LIST_MARKER_REGEX = re.compile(r"^(?:[-*+]|\d+[.)])(?:\s+\[[ xX]\])?(?:\s+|$)")

# Tag qui marque une section de tâches ; il n'entre pas dans le chemin (#240).
TODO_TAG = "TODO"


@dataclass
class TodoLine:
    """Ligne d'une section TODO : son chemin (titres de la section sans `TODO`,
    puis lignes parentes), son texte, et la ligne dont elle est la sous-tâche."""

    path: str
    text: str
    parent: TodoLine | None


def create_todo_from_dict(
    todo_data: dict, parent: Todo | None = None
) -> tuple[Todo, bool]:
    """Tâche d'une ligne de note, créée si elle n'existe pas encore.

    Elle est identifiée par la date de la note, son chemin et son texte (#240).
    Une tâche créée avant #240, sans chemin, est reprise par sa date et son
    texte : elle reçoit le chemin. Le parent n'est posé qu'à la création (#238) :
    une tâche existante garde le sien, qui a pu être choisi à la main. Pas
    d'échéance (#239) : elle se choisit dans le bilan qui suit l'enregistrement
    de la note. Renvoie la tâche, et si elle vient d'être créée.
    """
    identity = {
        "created_from_note": True,
        "note_part_date": todo_data["date"],
        "note_part_text": todo_data["content"],
    }
    todo = Todo.objects.filter(**identity, note_path=todo_data["path"]).first()
    if todo is not None:
        return todo, False
    todo = Todo.objects.filter(**identity, note_path="").first()
    if todo is not None:
        todo.note_path = todo_data["path"]
        todo.save(update_fields=["note_path"])
        return todo, False

    project, _ = Project.objects.get_or_create(name=todo_data["project"])
    subject = (
        Subject.objects.get_or_create(name=todo_data["subject"])[0]
        if todo_data.get("subject")
        else None
    )
    todo = Todo.objects.create(
        **identity,
        note_path=todo_data["path"],
        title=todo_data["content"],
        project=project,
        subject=subject,
        parent=parent,
    )
    tag_names = todo_data.get("tags", [])
    if tag_names:
        todo.tags.add(*[Tag.objects.get_or_create(name=name)[0] for name in tag_names])
    return todo, True


def todo_text(line: str) -> str:
    """Texte d'une ligne de TODO, sans marqueur de liste ni case (#222).

    Marqueurs Markdown : `-`, `*`, `+`, `1.`, `1)`, suivis d'une case `[ ]` ou
    `[x]` éventuelle ; une case cochée ne termine pas la tâche. Le texte est
    borné à la longueur des champs.
    """
    text = LIST_MARKER_REGEX.sub("", line.strip(), count=1)
    return text.strip()[:TODO_TEXT_MAX_LENGTH]


def todo_lines(note_part: NotePart) -> list[TodoLine]:
    """Lignes de tâches d'une note part marquée TODO, sans accès à la base.

    Une ligne imbriquée sous un élément de liste, selon la règle de Pandoc
    (#229), est une sous-tâche de cet élément (#238). Une ligne sans marqueur
    sous un élément est la suite de son texte : elle aussi devient sa sous-tâche.
    """
    headings = [
        title
        for title in note_part.heading_path.split(HEADING_SEPARATOR)
        if title and title != TODO_TAG
    ]
    lines: list[TodoLine] = []
    # Éléments ouverts, du plus extérieur au plus intérieur : colonne de leur
    # texte et ligne. Les colonnes croissent de l'extérieur vers l'intérieur.
    items: list[tuple[int, TodoLine]] = []
    for raw_line in note_part.content.split("\n"):
        text = todo_text(raw_line)
        if not text:
            continue
        indent = len(raw_line) - len(raw_line.lstrip(" "))
        depth = sum(1 for column, _ in items if indent >= column)
        container, parent = items[depth - 1] if depth else (0, None)

        ancestors = [line.text for _, line in items[:depth]]
        line = TodoLine(HEADING_SEPARATOR.join(headings + ancestors), text, parent)
        lines.append(line)

        item = LIST_ITEM_REGEX.match(raw_line)
        if item and indent < container + CODE_INDENT:
            items = [*items[:depth], (text_column(item), line)]
        elif not depth:
            # Ligne hors de toute liste : elle ferme les éléments ouverts.
            items = []
    return lines


def create_todos_from_note_part(note_part: NotePart) -> list[Todo]:
    """Une tâche par ligne d'une note part marquée TODO ; renvoie celles créées."""
    part_tags = [tag.name for tag in note_part.tags.all()]
    if TODO_TAG not in part_tags:
        return []

    subject = note_part.subject.name if note_part.subject else None
    tags = [tag for tag in part_tags if tag != TODO_TAG]
    created_todos: list[Todo] = []
    todos: dict[int, Todo] = {}
    for line in todo_lines(note_part):
        todo_data = {
            "date": note_part.note.date,
            "project": note_part.project.name,
            "path": line.path,
            "content": line.text,
            "subject": subject,
            "tags": tags,
        }
        parent = todos[id(line.parent)] if line.parent else None
        todo, created = create_todo_from_dict(todo_data, parent)
        todos[id(line)] = todo
        if created:
            created_todos.append(todo)
    return created_todos
