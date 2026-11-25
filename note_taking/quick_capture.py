"""Capture rapide (#386) : ajouter une ligne à la note du jour, sous un titre de son
plan, sans ouvrir l'éditeur.

La ligne va **en fin de section**, comme on l'écrirait à la main : après le texte du
titre choisi et avant ses sous-titres (sous un sous-titre, elle changerait de chemin).
Sans titre choisi, elle va en tête de la note, sans projet (#385). Elle ne tombe ni
dans un bloc de code, ni dans un bloc `:::`, et garde les fins de ligne de la note.

`targets` et `add_to_body` ne travaillent que sur du texte ; `capture` lit et écrit la
note du jour, en une transaction.
"""

import hashlib
import re
from dataclasses import dataclass

from django.db import transaction
from django.utils import timezone

from core.projects import clean_name
from core.sections import join_path

from .exceptions import NoteParseError, QuickCaptureError
from .models import Note
from .qmd.parser import (
    CODE_FENCE,
    FRONT_MATTER_DELIMITER,
    MAX_LEVEL,
    heading_name,
    parse_note,
)
from .renaming import Heading, headings, normalized
from .services import process_passages

TITLE_MAX_LENGTH = 200

# Autre clôture de code de Pandoc : le parseur l'ignore, le rendu la connaît.
TILDE_FENCE = "~~~"
DIV_CLOSE_REGEX = re.compile(r"^:{3,}$")
DIV_OPEN_REGEX = re.compile(r"^:{3,}\s*\S")
# Une ligne qui souligne celle d'au-dessus, et en fait un titre.
UNDERLINE_REGEX = re.compile(r"^(?:=+|-+)$")
TITLE_LINE_REGEX = re.compile(r"^#+\s")
BULLET_REGEX = re.compile(r"^[-*+]\s+(?:\[[ xX]\]\s+)?")
LINE_NUMBER_REGEX = re.compile(r"^Ligne \d+ : ")
LINE_REGEX = re.compile(r"[^\n]*\n|[^\n]+")


@dataclass(frozen=True)
class Target:
    """Un titre de la note du jour où écrire. `key` le retrouve quand la note a changé
    ailleurs : son chemin et son rang parmi les titres de même chemin."""

    key: str
    title: str
    depth: int
    project: str
    path: tuple[str, ...]
    heading: Heading

    @property
    def saved_path(self) -> str:
        """Le chemin comme on le saisit, pour les suggestions de niveaux (#90)."""
        return join_path(self.path)

    @property
    def can_nest(self) -> bool:
        return self.heading.level < MAX_LEVEL


def targets(body: str) -> list[Target]:
    """Le plan d'un texte de note : ses titres, comme l'analyse les reconnaît."""
    found: list[Target] = []
    seen: dict[tuple, int] = {}
    levels: list[int] = []
    for heading in headings(body):
        while levels and levels[-1] >= heading.level:
            levels.pop()
        identity = (heading.level, heading.project, heading.path)
        rank = seen.get(identity, 0)
        seen[identity] = rank + 1
        key = hashlib.sha256(repr((*identity, rank)).encode()).hexdigest()[:16]
        found.append(
            Target(
                key=key,
                title=heading_name(heading.title),
                depth=len(levels),
                project=heading.project or "",
                path=tuple(heading_name(title) for title in heading.path),
                heading=heading,
            )
        )
        levels.append(heading.level)
    return found


# Où écrire


@dataclass(frozen=True)
class Place:
    """Un rang de ligne (à partir de 0) où insérer, et si tous les blocs ouverts avant
    la fin de la zone y sont fermés."""

    position: int
    closed: bool


def last_place(lines: list[str], start: int, end: int) -> Place:
    """La place après le dernier texte de ces lignes, hors de tout bloc de code ou
    `:::` ouvert parmi elles, et sans sortir de celui où elles commencent."""
    position, depth, fence = start, 0, ""
    for index in range(start, end):
        line = lines[index].strip()
        if fence:
            if line.startswith(fence):
                fence = ""
        elif line.startswith((CODE_FENCE, TILDE_FENCE)):
            fence = line[:3]
        elif DIV_CLOSE_REGEX.match(line):
            depth -= 1
            if depth < 0:
                break
        elif DIV_OPEN_REGEX.match(line):
            depth += 1
        if line and not fence and depth == 0:
            position = index + 1
    return Place(position, closed=not fence and depth <= 0)


def own_end(lines: list[str], found: list[Target], target: Target | None) -> int:
    """La fin du texte propre d'un titre, avant le titre suivant ; sans titre, celle du
    texte en tête de la note."""
    start = target.heading.number if target else 0
    end = next(
        (
            other.heading.number - 1
            for other in found
            if target is None or other.heading.number > target.heading.number
        ),
        len(lines),
    )
    return last_place(lines, start, end).position


def branch_end(lines: list[str], found: list[Target], target: Target | None) -> int:
    """La fin d'un titre, sous-titres compris ; sans titre, celle de la note : la place
    d'un nouveau titre. Un bloc jamais fermé l'avalerait, ou le nouveau titre prendrait
    ce qui suit : refusé."""
    start = target.heading.number if target else 0
    end = next(
        (
            other.heading.number - 1
            for other in found
            if target
            and other.heading.number > target.heading.number
            and other.heading.level <= target.heading.level
        ),
        len(lines),
    )
    place = last_place(lines, start, end)
    if not place.closed:
        raise QuickCaptureError(
            "Un bloc de code ou « ::: » de la note n'est pas fermé : ajouter le titre "
            "dans l'éditeur."
        )
    return place.position


# Quoi écrire


def text_lines(text: str, is_task: bool) -> list[str]:
    """Les lignes à ajouter. Un texte qui ouvrirait un titre ou un bloc est refusé :
    il changerait la place de ce qui le suit."""
    lines = [line.rstrip() for line in text.strip().splitlines()]
    if is_task and lines:
        first = BULLET_REGEX.sub("", lines[0])
        # La suite d'une tâche reste dans son élément de liste.
        rest = [f"  {line}" if line else "" for line in lines[1:]]
        lines = [f"- [ ] {first}", *rest] if first else []
    if not lines:
        raise QuickCaptureError("Écrivez quelque chose à ajouter.")
    for line in lines:
        stripped = line.strip()
        if (
            TITLE_LINE_REGEX.match(stripped)
            or stripped.startswith((CODE_FENCE, TILDE_FENCE, ":::"))
            or UNDERLINE_REGEX.match(stripped)
            or stripped == FRONT_MATTER_DELIMITER
        ):
            raise QuickCaptureError(
                f"La ligne « {stripped} » ouvrirait un titre ou un bloc : l'écrire "
                "dans l'éditeur, ou choisir le titre dans le plan."
            )
    return lines


def follows_list(lines: list[str], position: int) -> bool:
    """Si la ligne d'avant est dans une liste à tirets, que la tâche continue."""
    for line in reversed(lines[:position]):
        if line.startswith("- "):
            return True
        if not line.startswith(" ") or not line.strip():
            return False
    return False


def insert(body: str, position: int, new_lines: list[str]) -> str:
    """Le texte avec ces lignes à ce rang, séparées par une ligne vide de ce qui les
    entoure (sauf la suite d'une liste), aux fins de ligne de la note."""
    raw = LINE_REGEX.findall(body)
    lines = [line.rstrip("\r\n") for line in raw]
    eol = "\r\n" if "\r\n" in body else "\n"

    added = list(new_lines)
    continues = added[0].startswith("- ") and follows_list(lines, position)
    if position and lines[position - 1].strip() and not continues:
        added.insert(0, "")
    if position < len(lines):
        following = lines[position].strip()
        if following and not DIV_CLOSE_REGEX.match(following):
            added.append("")

    block = [line + eol for line in added]
    if position and not raw[position - 1].endswith("\n"):
        # Après une dernière ligne sans fin de ligne : la nouvelle n'en a pas non plus.
        raw[position - 1] += eol
        block[-1] = added[-1]
    return "".join([*raw[:position], *block, *raw[position:]])


def add_to_body(
    body: str, text: str, key: str = "", is_task: bool = False, new_title: str = ""
) -> str:
    """Le texte de la note avec la capture : en fin de section du titre `key` (en tête
    sans titre), ou sous un nouveau titre, créé sous `key` (un projet sans `key`). Un
    titre de ce nom déjà écrit à cet endroit est repris."""
    added = text_lines(text, is_task)
    found = targets(body)
    target = next((other for other in found if other.key == key), None)
    if key and target is None:
        raise QuickCaptureError(
            "La note du jour a changé : le titre choisi n'y est plus. Choisir de "
            "nouveau où écrire."
        )
    lines = [line.rstrip("\r\n") for line in LINE_REGEX.findall(body)]

    title = clean_name(new_title)
    if title:
        known = child_named(found, target, title)
        if known is None:
            level = check_new_title(title, target)
            place = branch_end(lines, found, target)
            return insert(body, place, [f"{'#' * level} {title}", "", *added])
        target = known
    return insert(body, own_end(lines, found, target), added)


def child_named(
    found: list[Target], target: Target | None, title: str
) -> Target | None:
    """Le titre de ce nom (casse ignorée) juste sous `target`, ou le projet de ce nom
    sans `target`."""
    for other in found:
        if target is None:
            # Le nom d'un projet est son titre entier, attributs compris (#367).
            if other.heading.level == 1 and normalized(
                other.heading.title
            ) == normalized(title):
                return other
        elif (
            normalized(other.title) == normalized(title)
            and other.heading.project == target.heading.project
            and other.heading.path[:-1] == target.heading.path
            and within(found, other, target)
        ):
            return other
    return None


def within(found: list[Target], other: Target, target: Target) -> bool:
    """Si `other` est écrit sous `target`, et non sous un autre titre de même chemin."""
    if other.heading.number <= target.heading.number:
        return False
    return all(
        between.heading.level > target.heading.level
        for between in found
        if target.heading.number < between.heading.number <= other.heading.number
    )


def check_new_title(title: str, target: Target | None) -> int:
    """Le niveau (nombre de dièses) d'un nouveau titre sous `target`."""
    if len(title) > TITLE_MAX_LENGTH:
        raise QuickCaptureError(
            f"Un titre ne dépasse pas {TITLE_MAX_LENGTH} caractères."
        )
    if target is None:
        return 1
    if not target.can_nest:
        raise QuickCaptureError(
            f"« {target.title} » est au dernier niveau : pas de titre sous lui."
        )
    return target.heading.level + 1


@transaction.atomic
def capture(
    text: str, key: str = "", is_task: bool = False, new_title: str = ""
) -> Note:
    """Ajoute la capture à la note du jour, créée au besoin, et recalcule ses
    passages. Rien n'est écrit en cas d'erreur (`AppError`).

    Seuls les avertissements que la capture fait naître restent dans `note.warnings`
    (un nom proche d'un existant, #374) : ceux que la note avait déjà ne la concernent
    pas."""
    today = timezone.localdate()
    note = Note.objects.filter(date=today).first() or Note(date=today)
    known = known_warnings(note)
    note.body = add_to_body(note.body, text, key, is_task, new_title)
    note.save(source=Note.Source.CAPTURE)
    process_passages(note)
    note.warnings = tuple(
        warning
        for warning in note.warnings
        if LINE_NUMBER_REGEX.sub("", warning) not in known
    )
    return note


def known_warnings(note: Note) -> set[str]:
    """Les avertissements de l'analyse du texte actuel, sans leur numéro de ligne, que
    la capture décale ; aucun si ce texte ne s'analyse pas."""
    try:
        warnings = parse_note(str(note.date), note.body).warnings
    except NoteParseError:
        return set()
    return {LINE_NUMBER_REGEX.sub("", warning) for warning in warnings}
