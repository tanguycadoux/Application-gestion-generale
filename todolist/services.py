import re
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date

from django.db.models import CharField, Value
from django.db.models.functions import Cast, Concat

from core.models import Project, Tag
from core.sections import levels, section_for
from note_taking.exceptions import NoteRenameError
from note_taking.models import Note, NotePart
from note_taking.qmd.lists import CODE_INDENT, LIST_ITEM_REGEX, text_column
from note_taking.qmd.parser import (
    CODE_FENCE,
    HEADING_SEPARATOR,
    TODO_TAG,
    parse_note,
)
from note_taking.services import replace_image_paths

from .models import TODO_TEXT_MAX_LENGTH, Todo, update_ancestors_progress

# La case en tête du texte d'un élément de liste, vide (« [ ] ») ou cochée (« [x] »).
BOX_REGEX = re.compile(r"^\[(?P<state>[ xX])\](?:\s+|$)")


@dataclass
class TodoLine:
    """Ligne de tâche d'une note part : son chemin (titres de la section, puis
    éléments parents), son texte, et la tâche dont elle est la sous-tâche."""

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
    section = section_for(project, todo_data.get("sections", []))
    todo = Todo.objects.create(
        **identity,
        note_path=todo_data["path"],
        title=todo_data["content"],
        project=project,
        section=section,
        parent=parent,
        note_state=Todo.NoteState.TO_REVIEW,
    )
    tag_names = todo_data.get("tags", [])
    if tag_names:
        todo.tags.add(*[Tag.objects.get_or_create(name=name)[0] for name in tag_names])
    return todo, True


def todo_text(line: str) -> str:
    """Texte d'une ligne de tâche, sans marqueur de liste ni case (#222).

    Marqueurs de liste de Pandoc (`-`, `1.`, `a)`, `(ii)`, `#.`… : `qmd/lists.py`),
    suivis d'une case `[ ]` éventuelle. Le texte est borné à la longueur des champs.
    """
    text = line.strip()
    item = LIST_ITEM_REGEX.match(text)
    if item:
        text = text[item.end() :]
        box = BOX_REGEX.match(text)
        if box:
            text = text[box.end() :]
    return text.strip()[:TODO_TEXT_MAX_LENGTH]


def todo_lines(note_part: NotePart) -> list[TodoLine]:
    """Lignes de tâches d'une note part, sans accès à la base (#297) ; voir
    `lines_of`."""
    return lines_of(note_part.heading_path, note_part.content, is_todo_part(note_part))


def lines_of(heading_path: str, content: str, flagged: bool) -> list[TodoLine]:
    """Lignes de tâches d'un texte, sous les titres `heading_path` ; `flagged` si sa
    branche est marquée `todo: true`.

    - Une **case vide** (`- [ ] texte`) est une tâche, où qu'elle soit.
    - Dans une branche `todo: true` (tag `TODO`), **chaque élément de liste** en est
      une, avec ou sans case.
    - Une **case cochée** (`- [x]`) n'en est jamais une : elle est ignorée, comme
      une ligne qui n'est pas un élément de liste.

    Un élément imbriqué sous un autre, selon la règle de Pandoc (#229), est une
    sous-tâche de la tâche la plus proche au-dessus de lui (#238). Le texte des
    éléments parents, tâches ou non, entre dans le chemin de la ligne (#240).
    """
    headings = [title for title in heading_path.split(HEADING_SEPARATOR) if title]
    lines: list[TodoLine] = []
    # Éléments ouverts, du plus extérieur au plus intérieur : colonne de leur
    # texte, leur ligne s'ils sont une tâche, et leur texte. Les colonnes croissent
    # de l'extérieur vers l'intérieur.
    items: list[tuple[int, TodoLine | None, str]] = []
    in_code_block = False
    for raw_line in content.split("\n"):
        stripped = raw_line.strip()
        if stripped.startswith(CODE_FENCE):
            in_code_block = not in_code_block
            continue
        if in_code_block or not stripped:
            continue
        indent = len(raw_line) - len(raw_line.lstrip(" "))
        depth = sum(1 for column, _, _ in items if indent >= column)
        container = items[depth - 1][0] if depth else 0

        item = LIST_ITEM_REGEX.match(raw_line)
        text = todo_text(raw_line) if item else ""
        if not item or not text or indent >= container + CODE_INDENT:
            if not depth:
                # Ligne hors de toute liste : elle ferme les éléments ouverts.
                items = []
            continue

        box = BOX_REGEX.match(raw_line[item.end() :])
        is_task = (box.group("state") == " ") if box else flagged
        line = None
        if is_task:
            ancestors = [parent_text for _, _, parent_text in items[:depth]]
            parent = next(
                (found for _, found, _ in reversed(items[:depth]) if found), None
            )
            line = TodoLine(HEADING_SEPARATOR.join(headings + ancestors), text, parent)
            lines.append(line)
        items = [*items[:depth], (text_column(item), line, text)]
    return lines


def body_lines(note_date: date, body: str) -> list[list[TodoLine]]:
    """Les lignes de tâches de chaque note part d'un texte de note, dans l'ordre :
    ce que l'analyse en tirerait, sans toucher à la base (images exceptées)."""
    return [
        lines_of(
            HEADING_SEPARATOR.join(part.headings),
            replace_image_paths("\n".join(part.lines))[0],
            TODO_TAG in part.tags,
        )
        for part in parse_note(str(note_date), body).parts
    ]


def renamed_identities(
    note_date: date, old_body: str, new_body: str
) -> list[tuple[TodoLine, TodoLine]]:
    """Les lignes de tâches dont le chemin change quand des titres sont réécrits,
    avant et après (#299).

    Seuls des titres changent : les note parts et leurs lignes se retrouvent une à
    une, dans le même ordre. Si le renommage en fusionnait ou en séparait, elles ne
    se retrouvent plus et la note est refusée.
    """
    old, new = body_lines(note_date, old_body), body_lines(note_date, new_body)
    if len(old) != len(new) or any(
        len(a) != len(b) for a, b in zip(old, new, strict=True)
    ):
        raise NoteRenameError(
            f"Note du {note_date} : le renommage fusionnerait ou séparerait des "
            "parties de la note. Décocher son titre dans le bilan, ou lui garder son "
            "ancien nom."
        )
    return [
        (before, after)
        for part_before, part_after in zip(old, new, strict=True)
        for before, after in zip(part_before, part_after, strict=True)
        if (before.path, before.text) != (after.path, after.text)
    ]


def is_todo_part(note_part: NotePart) -> bool:
    return any(tag.name == TODO_TAG for tag in note_part.tags.all())


def move_tasks(note_date: date, moves: list[tuple[TodoLine, TodoLine]]) -> None:
    """Range les tâches déjà créées sous leur nouveau chemin : même fiche, seul le
    chemin de leur ligne change. En deux temps, pour qu'un chemin déjà pris par une
    tâche qui part aussi ne fasse pas échouer la contrainte d'unicité."""
    found = []
    for before, after in moves:
        todos = Todo.all_objects.filter(
            created_from_note=True,
            note_part_date=note_date,
            note_path=before.path,
            note_part_text=before.text,
        )
        found.append((list(todos.values_list("pk", flat=True)), after.path))
    for pks, _ in found:
        Todo.all_objects.filter(pk__in=pks).update(
            note_path=Concat(Value("\x1f"), Cast("pk", CharField()))
        )
    for pks, path in found:
        Todo.all_objects.filter(pk__in=pks).update(note_path=path)


def note_lines(note_parts: Iterable[NotePart]) -> set[tuple[str, str]]:
    """Chemin et texte des lignes de tâches d'une note : leur identité (#240)."""
    return {
        (line.path, line.text)
        for note_part in note_parts
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
    """Une tâche par ligne de tâche d'une note part ; renvoie celles créées."""
    part_tags = [tag.name for tag in note_part.tags.all()]

    sections = levels(note_part.section) if note_part.section else []
    tags = [tag for tag in part_tags if tag != TODO_TAG]
    created_todos: list[Todo] = []
    todos: dict[int, Todo] = {}
    for line in todo_lines(note_part):
        todo_data = {
            "date": note_part.note.date,
            "project": note_part.project.name,
            "path": line.path,
            "content": line.text,
            "sections": sections,
            "tags": tags,
        }
        parent = todos[id(line.parent)] if line.parent else None
        todo, created = create_todo_from_dict(todo_data, parent)
        todos[id(line)] = todo
        if created:
            created_todos.append(todo)
    return created_todos
