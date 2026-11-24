import re
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date

from django.db import transaction
from django.db.models import CharField, Value
from django.db.models.functions import Cast, Concat

from core.models import Tag
from core.projects import project_for
from core.sections import levels, section_for
from note_taking.exceptions import NoteRenameError
from note_taking.models import Note, Passage
from note_taking.qmd.lists import CODE_INDENT, LIST_ITEM_REGEX, text_column
from note_taking.qmd.parser import (
    CODE_FENCE,
    HEADING_SEPARATOR,
    TODO_TAG,
    heading_name,
    parse_note,
)
from note_taking.renaming import normalized
from note_taking.services import replace_image_paths

from .models import TASK_TEXT_MAX_LENGTH, Task
from .progress import update_ancestors_progress

# La case en tête du texte d'un élément de liste, vide (« [ ] ») ou cochée (« [x] »).
BOX_REGEX = re.compile(r"^\[(?P<state>[ xX])\](?:\s+|$)")


@dataclass
class TaskLine:
    """Ligne de tâche d'un passage : son chemin (titres de la section, puis
    éléments parents), son texte, et la tâche dont elle est la sous-tâche."""

    path: str
    text: str
    parent: TaskLine | None


def create_task_from_dict(
    task_data: dict, parent: Task | None = None
) -> tuple[Task, bool]:
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
        "note_date": task_data["date"],
        "note_line_text": task_data["content"],
    }
    task = Task.all_objects.filter(**identity, note_path=task_data["path"]).first()
    if task is not None:
        return task, False
    task = Task.all_objects.filter(**identity, note_path="").first()
    if task is not None:
        task.note_path = task_data["path"]
        task.save(update_fields=["note_path"])
        return task, False

    # Sans projet ni chemin : une case du texte avant le premier `#`, à ranger (#385).
    project = (
        project_for(task_data["project"])[0]
        if task_data["project"] is not None
        else None
    )
    section = section_for(project, task_data.get("sections", [])) if project else None
    task = Task.objects.create(
        **identity,
        note_path=task_data["path"],
        title=task_data["content"],
        project=project,
        section=section,
        parent=parent,
        note_state=Task.NoteState.TO_REVIEW,
    )
    tag_names = task_data.get("tags", [])
    if tag_names:
        task.tags.add(*[Tag.objects.get_or_create(name=name)[0] for name in tag_names])
    return task, True


def task_text(line: str) -> str:
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
    return text.strip()[:TASK_TEXT_MAX_LENGTH]


def task_lines(passage: Passage) -> list[TaskLine]:
    """Lignes de tâches d'un passage, sans accès à la base (#297) ; voir
    `lines_of`."""
    return lines_of(passage.heading_path, passage.content, is_todo_passage(passage))


def lines_of(heading_path: str, content: str, flagged: bool) -> list[TaskLine]:
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
    lines: list[TaskLine] = []
    # Éléments ouverts, du plus extérieur au plus intérieur : colonne de leur
    # texte, leur ligne s'ils sont une tâche, et leur texte. Les colonnes croissent
    # de l'extérieur vers l'intérieur.
    items: list[tuple[int, TaskLine | None, str]] = []
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
        text = task_text(raw_line) if item else ""
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
            line = TaskLine(HEADING_SEPARATOR.join(headings + ancestors), text, parent)
            lines.append(line)
        items = [*items[:depth], (text_column(item), line, text)]
    return lines


def body_lines(note_date: date, body: str) -> list[list[TaskLine]]:
    """Les lignes de tâches de chaque passage d'un texte de note, dans l'ordre :
    ce que l'analyse en tirerait, sans toucher à la base (images exceptées)."""
    return [
        lines_of(
            HEADING_SEPARATOR.join(passage.headings),
            replace_image_paths("\n".join(passage.lines))[0],
            TODO_TAG in passage.tags,
        )
        for passage in parse_note(str(note_date), body).passages
    ]


def renamed_identities(
    note_date: date, old_body: str, new_body: str
) -> list[tuple[TaskLine, TaskLine]]:
    """Les lignes de tâches dont le chemin change quand des titres sont réécrits,
    avant et après (#299).

    Seuls des titres changent : un passage par section écrite (#387), les passages
    et leurs lignes se retrouvent un à un, dans le même ordre (par précaution, la
    note est refusée sinon). Deux lignes de même texte qui se retrouveraient sous le
    même chemin seraient une seule tâche : la note est refusée aussi.
    """
    old, new = body_lines(note_date, old_body), body_lines(note_date, new_body)
    if len(old) != len(new) or any(
        len(a) != len(b) for a, b in zip(old, new, strict=True)
    ):
        raise NoteRenameError(
            f"Note du {note_date} : le renommage fusionnerait ou séparerait des "
            "passages de la note. Décocher son titre dans le bilan, ou lui garder son "
            "ancien nom."
        )
    before = {(line.path, line.text) for lines in old for line in lines}
    after = [(line.path, line.text) for lines in new for line in lines]
    if len(set(after)) < len(before):
        text = next(text for path, text in after if after.count((path, text)) > 1)
        raise NoteRenameError(
            f"Note du {note_date} : le renommage confondrait deux tâches « {text} » "
            "sous le même chemin. Décocher son titre dans le bilan, ou lui garder son "
            "ancien nom."
        )
    return [
        (before, after)
        for passage_before, passage_after in zip(old, new, strict=True)
        for before, after in zip(passage_before, passage_after, strict=True)
        if (before.path, before.text) != (after.path, after.text)
    ]


def follow_projects(note_date: date, old_body: str, new_body: str) -> None:
    """Quand un titre `#` est réécrit, les tâches de ses passages passent au projet
    du nouveau titre, et au niveau de même chemin sous ce projet (#170). Leur chemin
    de ligne a déjà suivi (`move_tasks`). Un projet qui ne change que de casse est le
    même (#374) : rien à faire."""
    old = parse_note(str(note_date), old_body).passages
    new = parse_note(str(note_date), new_body).passages
    if len(old) != len(new):
        return
    for before, after in zip(old, new, strict=True):
        if after.project is None or (
            before.project is not None
            and before.project.casefold() == after.project.casefold()
        ):
            continue
        project = project_for(after.project)[0]
        section = section_for(project, after.path)
        paths = {
            line.path
            for line in lines_of(
                HEADING_SEPARATOR.join(after.headings),
                replace_image_paths("\n".join(after.lines))[0],
                TODO_TAG in after.tags,
            )
        }
        Task.all_objects.filter(
            created_from_note=True, note_date=note_date, note_path__in=paths
        ).update(project=project, section=section)


def is_todo_passage(passage: Passage) -> bool:
    return any(tag.name == TODO_TAG for tag in passage.tags.all())


@transaction.atomic
def move_tasks(note_date: date, moves: list[tuple[TaskLine, TaskLine]]) -> None:
    """Range les tâches déjà créées sous leur nouveau chemin : même fiche, seul le
    chemin de leur ligne change. En deux temps, pour qu'un chemin déjà pris par une
    tâche qui part aussi ne fasse pas échouer la contrainte d'unicité ; en une
    transaction, pour ne jamais laisser un déplacement à moitié fait.

    Un chemin déjà pris par une tâche qui **ne part pas** (la même ligne a deux
    tâches, l'une restée sous l'ancien chemin, #170) n'est pas pris : la ligne
    retrouve cette tâche-là, et l'autre reste où elle est, à revoir dans le bilan."""
    found = []
    for before, after in moves:
        tasks = Task.all_objects.filter(
            created_from_note=True,
            note_date=note_date,
            note_path=before.path,
            note_line_text=before.text,
        )
        found.append((list(tasks.values_list("pk", flat=True)), after))
    moving = {pk for pks, _ in found for pk in pks}
    kept = [
        (pks, after.path)
        for pks, after in found
        if not Task.all_objects.filter(
            created_from_note=True,
            note_date=note_date,
            note_path=after.path,
            note_line_text=after.text,
        )
        .exclude(pk__in=moving)
        .exists()
    ]
    for pks, _ in kept:
        Task.all_objects.filter(pk__in=pks).update(
            note_path=Concat(Value("\x1f"), Cast("pk", CharField()))
        )
    for pks, path in kept:
        Task.all_objects.filter(pk__in=pks).update(note_path=path)


def note_lines(passages: Iterable[Passage]) -> set[tuple[str, str]]:
    """Chemin et texte des lignes de tâches d'une note : leur identité (#240)."""
    return {
        (line.path, line.text) for passage in passages for line in task_lines(passage)
    }


def origin_anchor(task: Task, note: Note) -> str:
    """L'identifiant du titre de la section où la tâche est écrite, dans la page de sa
    note d'origine (#375) ; vide pour ouvrir la note en haut.

    Le passage qui a sa ligne, donc la bonne occurrence d'un titre répété ; à défaut
    (ligne cochée ou retirée dans la note), le passage le plus profond parmi les titres
    de son chemin.
    """
    passages = list(note.passages.order_by("position").prefetch_related("tags"))
    for passage in passages:
        if (task.note_path, task.note_line_text) in note_lines([passage]):
            return passage.heading_id
    above = [
        passage
        for passage in passages
        if passage.heading_path
        and f"{task.note_path}{HEADING_SEPARATOR}".startswith(
            f"{passage.heading_path}{HEADING_SEPARATOR}"
        )
    ]
    closest = max(above, key=lambda passage: len(passage.heading_path), default=None)
    return closest.heading_id if closest else ""


def note_tasks_to_review(note_date: date):
    return Task.objects.filter(
        created_from_note=True,
        note_date=note_date,
        note_state=Task.NoteState.TO_REVIEW,
    )


def mark_gone_lines(note_date: date, lines: set[tuple[str, str]]) -> None:
    """Une tâche revue dont la ligne a disparu de la note redevient à revoir :
    le bilan propose de la garder, de l'écarter ou de la remplacer (#240)."""
    reviewed = Task.objects.filter(
        created_from_note=True,
        note_date=note_date,
        note_state=Task.NoteState.REVIEWED,
    )
    gone = [
        task.pk
        for task in reviewed
        if (task.note_path, task.note_line_text) not in lines
    ]
    Task.objects.filter(pk__in=gone).update(note_state=Task.NoteState.TO_REVIEW)


def visible_subtree(task: Task) -> list[Task]:
    """La tâche et ses sous-tâches affichées, à tous les niveaux."""
    subtree, level = [task], [task]
    while level:
        level = list(Task.objects.filter(parent__in=level))
        subtree += level
    return subtree


def removal_dismisses(task: Task) -> bool:
    """Retirer la tâche l'écarte-t-il ? Oui si son arbre contient une tâche issue
    d'une note (#290)."""
    return any(item.created_from_note for item in visible_subtree(task))


def remove_task(task: Task) -> None:
    """Écarte ou supprime une tâche et ses sous-tâches (#240, #290).

    Un arbre qui contient une tâche issue d'une note est écarté en entier, tâches
    saisies à la main comprises : il n'est plus affiché, le prochain
    enregistrement de la note ne recrée pas ses tâches, et le rétablir le rend
    intact. Un arbre saisi à la main est supprimé ; une tâche déjà écartée qu'il
    portait est détachée, pour ne pas partir avec lui.
    """
    subtree = visible_subtree(task)
    pks = [item.pk for item in subtree]
    if any(item.created_from_note for item in subtree):
        Task.objects.filter(pk__in=pks).update(note_state=Task.NoteState.DISMISSED)
    else:
        Task.all_objects.filter(
            parent__in=pks, note_state=Task.NoteState.DISMISSED
        ).update(parent=None)
        Task.all_objects.filter(pk__in=pks).delete()
    update_ancestors_progress(task.parent_id)


def dismissed_subtree(task: Task) -> list[Task]:
    """La tâche et ses sous-tâches écartées, à tous les niveaux."""
    subtree, level = [task], [task]
    while level:
        level = list(
            Task.all_objects.filter(
                parent__in=level, note_state=Task.NoteState.DISMISSED
            )
        )
        subtree += level
    return subtree


@dataclass
class DismissedRow:
    """Tâche écartée dont le parent ne l'est pas, avec ses sous-tâches écartées :
    ce que « Rétablir » remet ensemble (#290)."""

    task: Task
    subtasks: int
    note: Note | None
    # Texte de la confirmation, posé par la vue.
    confirm: str = ""


def top_dismissed():
    """Les tâches écartées dont le parent ne l'est pas : celles que la liste montre."""
    return Task.all_objects.filter(note_state=Task.NoteState.DISMISSED).exclude(
        parent__note_state=Task.NoteState.DISMISSED
    )


def dismissed_rows() -> list[DismissedRow]:
    dismissed = Task.all_objects.filter(
        note_state=Task.NoteState.DISMISSED
    ).select_related("project", "parent")
    tops = [
        task
        for task in dismissed.order_by("-note_date", "pk")
        if task.parent is None or task.parent.note_state != Task.NoteState.DISMISSED
    ]
    notes = Note.objects.in_bulk([task.note_date for task in tops], field_name="date")
    return [
        DismissedRow(task, len(dismissed_subtree(task)) - 1, notes.get(task.note_date))
        for task in tops
    ]


def restore_task(task: Task) -> Task | None:
    """Rétablit une tâche écartée et ses sous-tâches écartées (#290).

    Chacune redevient revue si sa ligne est encore dans sa note, gardée sans sa
    ligne sinon ; une tâche saisie à la main le redevient. La tâche retrouve son
    parent s'il est encore affiché ; s'il est écarté, elle est rétablie à la
    racine, et le parent écarté est renvoyé pour le signaler.
    """
    subtree = dismissed_subtree(task)
    notes = Note.objects.filter(
        date__in={item.note_date for item in subtree if item.created_from_note}
    )
    lines: dict[date | None, set[tuple[str, str]]] = {
        note.date: note_lines(note.passages.prefetch_related("tags")) for note in notes
    }
    states: dict[str, list[int]] = {}
    for item in subtree:
        if not item.created_from_note:
            state = ""
        elif (item.note_path, item.note_line_text) in lines.get(item.note_date, set()):
            state = Task.NoteState.REVIEWED
        else:
            state = Task.NoteState.DETACHED
        states.setdefault(state, []).append(item.pk)
    for state, pks in states.items():
        Task.all_objects.filter(pk__in=pks).update(note_state=state)

    dismissed_parent = None
    if task.parent_id and not Task.objects.filter(pk=task.parent_id).exists():
        dismissed_parent = task.parent
        Task.all_objects.filter(pk=task.pk).update(parent=None)
    else:
        update_ancestors_progress(task.parent_id)
    return dismissed_parent


def placed_by_note(task: Task) -> bool:
    """Si le projet et le niveau de la tâche sont ceux des titres de sa ligne, et non
    un choix fait à la main. Les éléments parents d'une ligne suivent ses titres dans
    son chemin : on en compare le début (un niveau remonté à la main dans le même
    chemin ne s'en distingue pas)."""
    place = [task.project.name] if task.project else []
    place += levels(task.section) if task.section else []
    titles = [
        heading_name(title)
        for title in task.note_path.split(HEADING_SEPARATOR)[: len(place)]
    ]
    return [normalized(name) for name in place] == [normalized(t) for t in titles]


def replace_task(old: Task, new: Task) -> None:
    """L'ancienne tâche, dont la ligne a disparu, prend la place de la tâche de
    la nouvelle ligne (#240) : elle garde avancement, échéance et sous-tâches, et
    reçoit celles de la nouvelle. Son titre suit la ligne, sauf s'il a été
    renommé à la main ; son projet et son niveau aussi (#382), sauf s'ils ont été
    choisis à la main, ou si la nouvelle ligne est dans le texte sans projet."""
    if new.project and placed_by_note(old):
        old.project, old.section = new.project, new.section
    if old.title == old.note_line_text:
        old.title = new.title
    Task.all_objects.filter(parent=new).update(parent=old)
    old.note_path, old.note_line_text = new.note_path, new.note_line_text
    new.delete()
    old.note_state = Task.NoteState.REVIEWED
    old.save()


def create_tasks_from_passage(passage: Passage) -> list[Task]:
    """Une tâche par ligne de tâche d'un passage ; renvoie celles créées."""
    passage_tags = [tag.name for tag in passage.tags.all()]

    sections = levels(passage.section) if passage.section else []
    tags = [tag for tag in passage_tags if tag != TODO_TAG]
    created_tasks: list[Task] = []
    tasks: dict[int, Task] = {}
    for line in task_lines(passage):
        task_data = {
            "date": passage.note.date,
            "project": passage.project.name if passage.project else None,
            "path": line.path,
            "content": line.text,
            "sections": sections,
            "tags": tags,
        }
        parent = tasks[id(line.parent)] if line.parent else None
        task, created = create_task_from_dict(task_data, parent)
        tasks[id(line)] = task
        if created:
            created_tasks.append(task)
    return created_tasks
