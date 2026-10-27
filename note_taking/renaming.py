"""Renommer un niveau de chemin : réécrire les titres des notes (#299).

Un niveau de chemin vient des titres des notes. Le renommer, c'est réécrire ces
titres. Un titre est repéré par **la suite des titres au-dessus de lui**, projet
compris, et pas par son niveau : `### Réunion` sans `##` au-dessus est le même
niveau que `## Réunion` (un niveau sauté n'est pas réécrit, #305).

Les titres suivent l'analyse du parseur : ceux d'un bloc de code ou d'un callout ne
comptent pas, et le texte entier du titre, attributs compris, est le nom du niveau.
La réécriture garde les fins de ligne.

`find_headings` et `rewrite_titles` ne travaillent que sur du texte ; le reste
(`find_occurrences`, `rename_titles`) lit et écrit les notes, dans une transaction.
"""

import re
from collections.abc import Iterable
from dataclasses import dataclass

from django.db import transaction
from django.urls import reverse

from core.app_registry import HeadingOccurrence
from core.models import Project
from core.sections import LABEL_SEPARATOR
from core.templatetags.ui import date_text

from .exceptions import NoteRenameError
from .models import Note
from .qmd.parser import BLOCK_END, CALLOUT_START, CODE_FENCE, MAX_LEVEL, TITLE_REGEX
from .services import process_note_parts
from .signals import note_headings_renamed

# Un titre, ligne entière : indentation, dièses, espaces, texte, espaces de fin (et
# le retour chariot d'une fin de ligne Windows).
HEADING_LINE_REGEX = re.compile(r"^(?P<before>\s*#+\s+)(?P<title>.*?)(?P<after>\s*)$")


@dataclass(frozen=True)
class Heading:
    """Un titre d'une note, avec ce qui est au-dessus de lui."""

    number: int  # numéro de ligne, à partir de 1
    level: int
    title: str
    project: str | None
    # Les titres de `##` à `######` au-dessus de lui, lui compris, tels qu'écrits.
    path: tuple[str, ...]

    @property
    def key(self) -> str:
        return str(self.number)


def normalized(name: str) -> str:
    """Un nom comme la base le compare : espaces réduits, casse ignorée."""
    return " ".join(name.split()).casefold()


def headings(body: str) -> list[Heading]:
    """Les titres d'un texte de note, avec leur projet et leur chemin."""
    found = []
    stack: dict[int, str] = {}
    in_code = in_callout = False
    for index, line in enumerate(body.split("\n")):
        stripped = line.strip()
        if not in_code:
            if stripped.startswith(CALLOUT_START):
                in_callout = True
                continue
            if in_callout and stripped == BLOCK_END:
                in_callout = False
                continue
        if stripped.startswith(CODE_FENCE):
            in_code = not in_code
        match = TITLE_REGEX.match(stripped)
        if not match or in_code or in_callout:
            continue
        level = len(match.group(1))
        if level > MAX_LEVEL:
            continue
        stack[level] = match.group(2).strip()
        for deeper in [other for other in stack if other > level]:
            del stack[deeper]
        found.append(
            Heading(
                index + 1,
                level,
                stack[level],
                stack.get(1),
                tuple(stack[other] for other in sorted(stack) if other >= 2),
            )
        )
    return found


def find_headings(body: str, project: str, levels: list[str]) -> list[Heading]:
    """Les titres de ce texte qui sont ce niveau de chemin, sous ce projet."""
    wanted = [normalized(level) for level in levels]
    return [
        heading
        for heading in headings(body)
        if heading.project == project
        and [normalized(title) for title in heading.path] == wanted
    ]


def rewrite_titles(body: str, numbers: Iterable[int], new_title: str) -> str:
    """Le texte dont les titres des lignes `numbers` (à partir de 1) portent
    `new_title`. Dièses, espaces et fin de ligne sont gardés."""
    wanted = set(numbers)
    lines = body.split("\n")
    for number in wanted:
        match = HEADING_LINE_REGEX.match(lines[number - 1])
        if match is None:  # pragma: no cover - un titre repéré s'écrit toujours ainsi
            raise NoteRenameError(f"Ligne {number} : ce n'est pas un titre.")
        lines[number - 1] = f"{match['before']}{new_title}{match['after']}"
    return "\n".join(lines)


@dataclass(frozen=True)
class Located:
    note: Note
    heading: Heading

    @property
    def key(self) -> str:
        return f"{self.note.pk}:{self.heading.number}"


def located(project: Project, levels: list[str]) -> list[Located]:
    return [
        Located(note, heading)
        for note in Note.objects.order_by("date")
        for heading in find_headings(note.body, project.name, levels)
    ]


def find_occurrences(project: Project, levels: list[str]) -> list[HeadingOccurrence]:
    """Les titres à réécrire pour renommer ce niveau, pour le bilan."""
    return [
        HeadingOccurrence(
            key=found.key,
            where=(
                f"Note du {date_text(found.note.date, 'moyen')}, "
                f"ligne {found.heading.number}"
            ),
            url=reverse("note_taking:note_detail", args=[found.note.date]),
            chain=LABEL_SEPARATOR.join([project.name, *found.heading.path]),
        )
        for found in located(project, levels)
    ]


def rename_titles(
    project: Project, levels: list[str], new_name: str, keys: list[str]
) -> list[str]:
    """Réécrit les titres choisis (`keys`, ceux du bilan) avec `new_name`, puis
    recalcule les notes. Renvoie les phrases du compte rendu.

    Atomique. Si une note a changé depuis le bilan (un titre choisi n'est plus ce
    niveau, ou plus à cette ligne), rien n'est écrit.
    """
    with transaction.atomic():
        current = {found.key: found for found in located(project, levels)}
        stale = [key for key in keys if key not in current]
        if stale:
            raise NoteRenameError(
                "Une note a changé depuis le bilan : un titre choisi n'est plus ce "
                "niveau. Rien n'a été modifié ; recommencer depuis le bilan."
            )
        chosen: dict[Note, list[int]] = {}
        for key in keys:
            found = current[key]
            chosen.setdefault(found.note, []).append(found.heading.number)

        for note, numbers in chosen.items():
            old_body = note.body
            new_body = rewrite_titles(old_body, numbers, new_name)
            note.body = new_body
            note.save()
            note_headings_renamed.send(
                sender=Note, note=note, old_body=old_body, new_body=new_body
            )
            process_note_parts(note)

    titles = "titres réécrits" if len(keys) > 1 else "titre réécrit"
    notes = "notes" if len(chosen) > 1 else "note"
    return [f"{len(keys)} {titles} dans {len(chosen)} {notes}."]
