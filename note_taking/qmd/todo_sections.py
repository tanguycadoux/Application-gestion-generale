"""Conversion des sections `TODO` d'une note en cases à cocher (#297).

Avant #297, un titre `TODO` (de `###` à `######`) marquait une section de tâches :
chaque ligne y était une tâche. Maintenant une tâche est une case `- [ ] texte`.
Un titre `TODO` de niveau `##` n'était alors qu'un niveau de chemin ordinaire ; il est
converti de la même façon (#322), le niveau `#` restant un projet.
Cette conversion réécrit le texte d'une note : le titre `TODO` est retiré, et
chaque élément de liste de sa section reçoit sa case.

**Le titre retiré change le chemin des tâches** quand il suit un titre de même
niveau : `### Compte rendu` puis `### TODO` donnait aux tâches le chemin sans
« Compte rendu » (le titre `TODO` l'avait remplacé) ; une fois `### TODO` retiré,
la liste est sous « Compte rendu ». La conversion garde donc, pour chaque
morceau de section, les titres d'avant et d'après (`Chunk`), pour que l'appelant
puisse ranger sous leur nouveau chemin les tâches déjà créées (#240).

Le texte d'une section TODO qui n'est pas qu'une liste (paragraphe, bloc de
métadonnées, case cochée, code) ne se convertit pas seul : la note est signalée,
et laissée telle quelle.

**Sans accès à la base** : la fonction ne lit ni n'écrit que du texte, dans les
mêmes fins de ligne que la note.
"""

import re
from dataclasses import dataclass, field

from .lists import LIST_ITEM_REGEX
from .parser import (
    BLOCK_END,
    CALLOUT_START,
    CODE_FENCE,
    MAX_LEVEL,
    METADATA_BLOCK_START,
    TITLE_REGEX,
)

TODO_TITLE = "TODO"
# Le niveau 1 est un projet, jamais une section.
MIN_TODO_LEVEL = 2
# Une case en tête du texte d'un élément : « [ ] » vide, « [x] » cochée.
BOX_REGEX = re.compile(r"^\[(?P<state>[ xX])\](?:\s|$)")


@dataclass(frozen=True)
class Change:
    """Une ligne modifiée (`after`) ou retirée (`after` vaut None)."""

    number: int
    before: str
    after: str | None


@dataclass(frozen=True)
class BoxLine:
    """Une case rencontrée hors des sections TODO."""

    number: int
    text: str


@dataclass
class Chunk:
    """Les lignes d'une section TODO sous un même contexte de titres, avant et
    après la conversion, avec les titres d'alors (sans `TODO`) et d'après."""

    old_headings: list[str]
    new_headings: list[str]
    before: list[str] = field(default_factory=list)
    after: list[str] = field(default_factory=list)


@dataclass
class Conversion:
    body: str
    changes: list[Change] = field(default_factory=list)
    problems: list[str] = field(default_factory=list)
    chunks: list[Chunk] = field(default_factory=list)
    # Hors des sections TODO : les cases vides deviendront des tâches, les cases
    # cochées sont ignorées.
    open_boxes: list[BoxLine] = field(default_factory=list)
    done_boxes: list[BoxLine] = field(default_factory=list)
    sections: int = 0


def heading_level(line: str) -> tuple[int, str] | None:
    match = TITLE_REGEX.match(line.strip())
    if not match:
        return None
    return len(match.group(1)), match.group(2).strip()


def is_todo_heading(line: str) -> int | None:
    """Niveau du titre si c'est un titre `TODO` de `##` à `######`."""
    found = heading_level(line)
    if found and MIN_TODO_LEVEL <= found[0] <= MAX_LEVEL and found[1] == TODO_TITLE:
        return found[0]
    return None


def convert_item(line: str) -> tuple[str, str]:
    """(nature, ligne convertie) d'une ligne d'une section TODO.

    Natures : `blank`, `heading`, `box` (case vide, gardée), `done` (case cochée),
    `item` (élément converti), `empty` (marqueur seul), `other` (à la main).
    """
    stripped = line.strip()
    if not stripped:
        return "blank", line
    if heading_level(line):
        return "heading", line
    item = LIST_ITEM_REGEX.match(line)
    if not item:
        return "other", line
    rest = line[item.end() :]
    box = BOX_REGEX.match(rest)
    if box:
        return ("box" if box.group("state") == " " else "done"), line
    if not rest.strip():
        return "empty", line
    return "item", f"{line[: item.end()]}[ ] {rest}"


def apply_heading(stack: dict[int, str], level: int, title: str) -> None:
    """Un titre remplace son niveau et efface les niveaux plus profonds."""
    stack[level] = title
    for deeper in [other for other in stack if other > level]:
        del stack[deeper]


def titles(stack: dict[int, str]) -> list[str]:
    return [stack[level] for level in sorted(stack)]


class Converter:
    def __init__(self, body: str):
        self.lines = body.split("\n")
        self.result = Conversion(body=body)
        self.out: list[str] = []
        # Titres de la note telle qu'elle est, et telle qu'elle sera sans les
        # titres `TODO` (qui ne remplacent plus leurs frères).
        self.old: dict[int, str] = {}
        self.new: dict[int, str] = {}

    def run(self) -> Conversion:
        in_code = in_callout = False
        index = 0
        while index < len(self.lines):
            line = self.lines[index]
            stripped = line.strip()
            if stripped.startswith(CODE_FENCE):
                in_code = not in_code
            elif not in_code and stripped.startswith(CALLOUT_START):
                in_callout = True
            elif not in_code and in_callout and stripped == BLOCK_END:
                in_callout = False

            found = None if in_code or in_callout else heading_level(line)
            if found and found[0] <= MAX_LEVEL and is_todo_heading(line):
                index = self.convert_section(index, found[0])
                continue
            if found and found[0] <= MAX_LEVEL:
                apply_heading(self.old, *found)
                apply_heading(self.new, *found)
            elif not in_code:
                self.note_box(index, line)
            self.out.append(line)
            index += 1

        if not self.result.problems:
            self.result.body = "\n".join(self.out)
        else:
            self.result.changes = []
        return self.result

    def note_box(self, index: int, line: str) -> None:
        item = LIST_ITEM_REGEX.match(line)
        if not item:
            return
        rest = line[item.end() :]
        found = BOX_REGEX.match(rest)
        if found:
            boxes = (
                self.result.open_boxes
                if found.group("state") == " "
                else self.result.done_boxes
            )
            boxes.append(BoxLine(index + 1, rest.strip()))

    def section_end(self, start: int, level: int) -> int:
        """Fin de la section : le prochain titre de même niveau ou moins profond."""
        in_code = False
        end = start + 1
        while end < len(self.lines):
            current = self.lines[end]
            if current.strip().startswith(CODE_FENCE):
                in_code = not in_code
            heading = None if in_code else heading_level(current)
            if heading and heading[0] <= level:
                break
            end += 1
        return end

    def new_chunk(self) -> Chunk:
        # Un titre `TODO` n'entrait pas dans le chemin des tâches.
        old = [title for title in titles(self.old) if title != TODO_TITLE]
        return Chunk(old_headings=old, new_headings=titles(self.new))

    def convert_section(self, start: int, level: int) -> int:
        """Convertit la section dont le titre `TODO` est à la ligne `start` ;
        renvoie l'indice de la ligne qui la suit."""
        result = self.result
        result.sections += 1
        end = self.section_end(start, level)
        # Le titre `TODO` remplace ses frères dans la note telle qu'elle était, pas
        # dans la note telle qu'elle sera.
        apply_heading(self.old, level, TODO_TITLE)

        converted: list[str] = []
        chunk = self.new_chunk()
        in_code = in_block = False
        for offset, line in enumerate(self.lines[start + 1 : end]):
            number = start + 2 + offset
            stripped = line.strip()
            if in_code or in_block:
                # Un seul point signalé par bloc : ses lignes passent telles quelles.
                if in_code and stripped.startswith(CODE_FENCE):
                    in_code = False
                if in_block and stripped == BLOCK_END:
                    in_block = False
                converted.append(line)
                continue
            if stripped.startswith(CODE_FENCE):
                in_code = True
                result.problems.append(
                    f"Ligne {number} : du code dans une section TODO."
                )
                converted.append(line)
                continue
            if stripped == METADATA_BLOCK_START or stripped.startswith(CALLOUT_START):
                in_block = True
                result.problems.append(
                    f"Ligne {number} : un bloc ({stripped}) dans une section TODO ; "
                    "il s'appliquerait à toute la branche une fois le titre retiré."
                )
                converted.append(line)
                continue

            nature, new_line = convert_item(line)
            if nature == "heading":
                if is_todo_heading(line):
                    result.problems.append(
                        f"Ligne {number} : un titre TODO dans une section TODO."
                    )
                else:
                    # Un titre plus profond reste, et ses lignes ont leurs titres.
                    if chunk.before:
                        result.chunks.append(chunk)
                    found = heading_level(line)
                    if found and found[0] <= MAX_LEVEL:
                        apply_heading(self.old, *found)
                        apply_heading(self.new, *found)
                    chunk = self.new_chunk()
                converted.append(line)
                continue
            if nature == "done":
                result.problems.append(
                    f"Ligne {number} : une case cochée dans une section TODO "
                    "(elle était une tâche, elle serait ignorée)."
                )
            elif nature == "other":
                result.problems.append(
                    f"Ligne {number} : « {stripped[:60]} » n'est pas un élément de "
                    "liste (seuls les éléments de liste sont des tâches)."
                )
            if new_line != line:
                result.changes.append(Change(number, line, new_line))
            chunk.before.append(line)
            chunk.after.append(new_line)
            converted.append(new_line)
        if chunk.before:
            result.chunks.append(chunk)

        result.changes.append(Change(start + 1, self.lines[start], None))
        # Le titre disparaît, avec la ligne vide qui le suit, sauf après un
        # paragraphe : Pandoc veut une ligne vide avant une liste.
        previous = self.out[-1].strip() if self.out else ""
        if (
            converted
            and not converted[0].strip()
            and (not previous or heading_level(previous))
        ):
            converted = converted[1:]
            result.changes.append(Change(start + 2, self.lines[start + 1], None))
        self.out.extend(converted)
        return end


def convert_todo_sections(body: str) -> Conversion:
    """Convertit les sections `TODO` d'un texte de note ; voir le module."""
    return Converter(body).run()
