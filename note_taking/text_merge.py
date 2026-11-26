"""Comparer les versions d'une note, ligne à ligne (#471).

L'éditeur renvoie, avec le texte saisi, le texte de la note tel qu'il l'a ouvert
(`original`). Quand la note a changé depuis, la comparaison de ce texte avec la
version enregistrée dit ce qui a changé ailleurs, et sous quel titre.
"""

import re
from dataclasses import dataclass, field
from difflib import SequenceMatcher

from .qmd.links import FENCE_REGEX
from .qmd.parser import HEADING_SEPARATOR

HEADING_REGEX = re.compile(r"^(#{1,6})\s+(.*?)\s*(?:\{[^}]*\})?\s*$")


def lines_of(text: str) -> list[str]:
    """Les lignes d'un texte, fins de ligne Windows comprises."""
    return text.replace("\r\n", "\n").split("\n")


@dataclass(frozen=True)
class Hunk:
    """Les lignes `start` à `end` (exclue) d'un texte, remplacées par `lines`."""

    start: int
    end: int
    lines: tuple[str, ...]
    # Position des nouvelles lignes dans l'autre texte.
    other_start: int = 0


def hunks(base: list[str], other: list[str]) -> list[Hunk]:
    """Ce qui change de `base` à `other`, dans l'ordre."""
    matcher = SequenceMatcher(None, base, other, autojunk=False)
    return [
        Hunk(i1, i2, tuple(other[j1:j2]), j1)
        for tag, i1, i2, j1, j2 in matcher.get_opcodes()
        if tag != "equal"
    ]


def heading_paths(lines: list[str]) -> list[str]:
    """Pour chaque ligne, les titres sous lesquels elle se trouve : « P › R »."""
    paths = []
    stack: list[tuple[int, str]] = []
    fence = None
    for line in lines:
        paths.append(HEADING_SEPARATOR.join(title for _, title in stack))
        opening = FENCE_REGEX.match(line)
        if fence is not None:
            if opening and opening.group(1)[0] == fence:
                fence = None
            continue
        if opening:
            fence = opening.group(1)[0]
            continue
        heading = HEADING_REGEX.match(line)
        if heading:
            level = len(heading.group(1))
            stack = [(lvl, title) for lvl, title in stack if lvl < level]
            stack.append((level, heading.group(2)))
    return paths


def plural(count: int, words: str) -> str:
    """« 1 ligne ajoutée », « 2 lignes ajoutées » : chaque mot prend la marque."""
    if count > 1:
        words = " ".join(f"{word}s" for word in words.split())
    return f"{count} {words}"


@dataclass
class Change:
    """Un endroit où la version enregistrée diffère de la version ouverte."""

    # Titres sous lesquels a lieu le changement ; vide avant le premier titre.
    where: str
    added: list[str] = field(default_factory=list)
    removed: list[str] = field(default_factory=list)

    @property
    def summary(self) -> str:
        added, removed = len(self.added), len(self.removed)
        if not removed:
            return plural(added, "ligne ajoutée")
        if not added:
            return plural(removed, "ligne retirée")
        return f"{plural(added, 'ligne ajoutée')}, {plural(removed, 'retirée')}"


def describe_changes(opened: str, saved: str) -> list[Change]:
    """Ce qui a changé de la version ouverte à la version enregistrée. Les lignes
    vides ne comptent pas : seules, elles ne font pas un changement."""
    base, other = lines_of(opened), lines_of(saved)
    paths = heading_paths(other)
    changes = []
    for hunk in hunks(base, other):
        added = [line for line in hunk.lines if line.strip()]
        removed = [line for line in base[hunk.start : hunk.end] if line.strip()]
        if added or removed:
            where = paths[min(hunk.other_start, len(paths) - 1)]
            changes.append(Change(where, added, removed))
    return changes


# Fusion (#472)


@dataclass
class Merge:
    """Le texte fusionné, et ce que l'éditeur doit changer au texte saisi pour y
    arriver : les lignes `from` à `to` (exclue) remplacées par `lines`."""

    text: str
    edits: list[dict] = field(default_factory=list)


def touches(first: Hunk, second: Hunk) -> bool:
    """Deux changements qui touchent les mêmes lignes, ou des lignes voisines : deux
    ajouts au même endroit, une ligne modifiée juste après une autre…"""
    return first.start <= second.end and second.start <= first.end


def merge_texts(original: str, mine: str, saved: str) -> Merge | None:
    """Le texte saisi (`mine`) et la version enregistrée (`saved`), partis tous deux
    du texte ouvert par l'éditeur (`original`) : réunis si leurs changements ne se
    touchent pas, rien sinon.

    Chaque ligne du résultat vient du texte saisi ou de la version enregistrée : un
    texte d'origine faux ne peut faire écrire que ce que l'un des deux contient. Les
    fins de ligne sont celles du texte saisi.
    """
    base = lines_of(original)
    mine_lines, saved_lines = lines_of(mine), lines_of(saved)
    ours, theirs = hunks(base, mine_lines), hunks(base, saved_lines)
    if any(touches(a, b) for a in ours for b in theirs):
        return None

    result: list[str] = []
    edits = []
    position = 0
    # Décalage des lignes du texte saisi par rapport au texte d'origine, avant le
    # changement en cours.
    shift = 0
    changes = [(hunk, False) for hunk in ours] + [(hunk, True) for hunk in theirs]
    for hunk, from_saved in sorted(changes, key=lambda change: change[0].start):
        result.extend(base[position : hunk.start])
        result.extend(hunk.lines)
        if from_saved:
            start = hunk.start + shift
            edits.append(
                {
                    "from": start,
                    "to": start + hunk.end - hunk.start,
                    "lines": list(hunk.lines),
                }
            )
        else:
            shift += len(hunk.lines) - (hunk.end - hunk.start)
        position = hunk.end
    result.extend(base[position:])
    newline = "\r\n" if "\r\n" in mine else "\n"
    return Merge(newline.join(result), edits)


def apply_edits(text: str, edits: list[dict]) -> str:
    """Le texte avec les changements de `Merge.edits`, comme l'éditeur les applique."""
    lines = lines_of(text)
    newline = "\r\n" if "\r\n" in text else "\n"
    for edit in reversed(edits):
        lines[edit["from"] : edit["to"]] = edit["lines"]
    return newline.join(lines)
