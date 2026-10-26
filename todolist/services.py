import re
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date

from core.models import Project, Subject, Tag
from note_taking.models import Note, NotePart
from note_taking.qmd.lists import CODE_INDENT, LIST_ITEM_REGEX, text_column
from note_taking.qmd.parser import HEADING_SEPARATOR

from .models import TODO_TEXT_MAX_LENGTH, Todo, update_ancestors_progress

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

    Elle est identifiée par la date de la note, son chemin et son texte (#240),
    écartée comprise : une tâche écartée n'est pas recréée. Une tâche créée avant
    #240, sans chemin, est reprise par sa date et son texte : elle reçoit le
    chemin. Une tâche créée est à revoir. Le parent n'est posé qu'à la création (#238) :
    une tâche existante garde le sien, qui a pu être choisi à la main. Pas
    d'échéance (#239) : elle se choisit dans le bilan qui suit l'enregistrement
    de la note. Renvoie la tâche, et si elle vient d'être créée.
    """
    identity = {
        "created_from_note": True,
        "note_part_date": todo_data["date"],
        "note_part_text": todo_data["content"],
    }
    todo = Todo.all_objects.filter(**identity, note_path=todo_data["path"]).first()
    if todo is not None:
        return todo, False
    todo = Todo.all_objects.filter(**identity, note_path="").first()
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
        note_state=Todo.NoteState.TO_REVIEW,
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


def is_todo_part(note_part: NotePart) -> bool:
    return any(tag.name == TODO_TAG for tag in note_part.tags.all())


def note_lines(note_parts: Iterable[NotePart]) -> set[tuple[str, str]]:
    """Chemin et texte des lignes de tâches d'une note : leur identité (#240)."""
    return {
        (line.path, line.text)
        for note_part in note_parts
        if is_todo_part(note_part)
        for line in todo_lines(note_part)
    }


def note_todos_to_review(note_date: date):
    return Todo.objects.filter(
        created_from_note=True,
        note_part_date=note_date,
        note_state=Todo.NoteState.TO_REVIEW,
    )


def mark_gone_lines(note_date: date, lines: set[tuple[str, str]]) -> None:
    """Une tâche revue dont la ligne a disparu de la note redevient à revoir :
    le bilan propose de la garder, de l'écarter ou de la remplacer (#240)."""
    reviewed = Todo.objects.filter(
        created_from_note=True,
        note_part_date=note_date,
        note_state=Todo.NoteState.REVIEWED,
    )
    gone = [
        todo.pk
        for todo in reviewed
        if (todo.note_path, todo.note_part_text) not in lines
    ]
    Todo.objects.filter(pk__in=gone).update(note_state=Todo.NoteState.TO_REVIEW)


def visible_subtree(todo: Todo) -> list[Todo]:
    """La tâche et ses sous-tâches affichées, à tous les niveaux."""
    subtree, level = [todo], [todo]
    while level:
        level = list(Todo.objects.filter(parent__in=level))
        subtree += level
    return subtree


def removal_dismisses(todo: Todo) -> bool:
    """Retirer la tâche l'écarte-t-il ? Oui si son arbre contient une tâche issue
    d'une note (#290)."""
    return any(task.created_from_note for task in visible_subtree(todo))


def remove_task(todo: Todo) -> None:
    """Écarte ou supprime une tâche et ses sous-tâches (#240, #290).

    Un arbre qui contient une tâche issue d'une note est écarté en entier, tâches
    saisies à la main comprises : il n'est plus affiché, le prochain
    enregistrement de la note ne recrée pas ses tâches, et le rétablir le rend
    intact. Un arbre saisi à la main est supprimé ; une tâche déjà écartée qu'il
    portait est détachée, pour ne pas partir avec lui.
    """
    subtree = visible_subtree(todo)
    pks = [task.pk for task in subtree]
    if any(task.created_from_note for task in subtree):
        Todo.objects.filter(pk__in=pks).update(note_state=Todo.NoteState.DISMISSED)
    else:
        Todo.all_objects.filter(
            parent__in=pks, note_state=Todo.NoteState.DISMISSED
        ).update(parent=None)
        Todo.all_objects.filter(pk__in=pks).delete()
    update_ancestors_progress(todo.parent_id)


def dismissed_subtree(todo: Todo) -> list[Todo]:
    """La tâche et ses sous-tâches écartées, à tous les niveaux."""
    subtree, level = [todo], [todo]
    while level:
        level = list(
            Todo.all_objects.filter(
                parent__in=level, note_state=Todo.NoteState.DISMISSED
            )
        )
        subtree += level
    return subtree


@dataclass
class DismissedRow:
    """Tâche écartée dont le parent ne l'est pas, avec ses sous-tâches écartées :
    ce que « Rétablir » remet ensemble (#290)."""

    task: Todo
    subtasks: int
    note: Note | None
    # Texte de la confirmation, posé par la vue.
    confirm: str = ""


def dismissed_rows() -> list[DismissedRow]:
    dismissed = Todo.all_objects.filter(
        note_state=Todo.NoteState.DISMISSED
    ).select_related("project", "parent")
    tops = [
        task
        for task in dismissed.order_by("-note_part_date", "pk")
        if task.parent is None or task.parent.note_state != Todo.NoteState.DISMISSED
    ]
    notes = Note.objects.in_bulk(
        [task.note_part_date for task in tops], field_name="date"
    )
    return [
        DismissedRow(
            task, len(dismissed_subtree(task)) - 1, notes.get(task.note_part_date)
        )
        for task in tops
    ]


def restore_task(todo: Todo) -> Todo | None:
    """Rétablit une tâche écartée et ses sous-tâches écartées (#290).

    Chacune redevient revue si sa ligne est encore dans sa note, gardée sans sa
    ligne sinon ; une tâche saisie à la main le redevient. La tâche retrouve son
    parent s'il est encore affiché ; s'il est écarté, elle est rétablie à la
    racine, et le parent écarté est renvoyé pour le signaler.
    """
    subtree = dismissed_subtree(todo)
    notes = Note.objects.filter(
        date__in={task.note_part_date for task in subtree if task.created_from_note}
    )
    lines: dict[date | None, set[tuple[str, str]]] = {
        note.date: note_lines(note.parts.prefetch_related("tags")) for note in notes
    }
    states: dict[str, list[int]] = {}
    for task in subtree:
        if not task.created_from_note:
            state = ""
        elif (task.note_path, task.note_part_text) in lines.get(
            task.note_part_date, set()
        ):
            state = Todo.NoteState.REVIEWED
        else:
            state = Todo.NoteState.DETACHED
        states.setdefault(state, []).append(task.pk)
    for state, pks in states.items():
        Todo.all_objects.filter(pk__in=pks).update(note_state=state)

    dismissed_parent = None
    if todo.parent_id and not Todo.objects.filter(pk=todo.parent_id).exists():
        dismissed_parent = todo.parent
        Todo.all_objects.filter(pk=todo.pk).update(parent=None)
    else:
        update_ancestors_progress(todo.parent_id)
    return dismissed_parent


def replace_task(old: Todo, new: Todo) -> None:
    """L'ancienne tâche, dont la ligne a disparu, prend la place de la tâche de
    la nouvelle ligne (#240) : elle garde avancement, échéance et sous-tâches, et
    reçoit celles de la nouvelle. Son titre suit la ligne, sauf s'il a été
    renommé à la main."""
    if old.title == old.note_part_text:
        old.title = new.title
    Todo.all_objects.filter(parent=new).update(parent=old)
    old.note_path, old.note_part_text = new.note_path, new.note_part_text
    new.delete()
    old.note_state = Todo.NoteState.REVIEWED
    old.save()


def create_todos_from_note_part(note_part: NotePart) -> list[Todo]:
    """Une tâche par ligne d'une note part marquée TODO ; renvoie celles créées."""
    if not is_todo_part(note_part):
        return []
    part_tags = [tag.name for tag in note_part.tags.all()]

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
