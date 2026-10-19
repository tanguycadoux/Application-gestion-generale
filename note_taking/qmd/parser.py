"""Analyse du contenu d'une note qmd en note parts.

Une note est découpée selon ses titres :

- `#` : projet ;
- `##` : sujet ;
- `###` à `######` : tags, cumulés en profondeur.

Des blocs `::: {.metadata}` ajoutent des tags au niveau de titre courant.
Le texte partageant le même projet, le même sujet et les mêmes tags forme
une note part.
"""

import re
from dataclasses import dataclass, field

from ..exceptions import NoteParseError

MAX_LEVEL = 6

TITLE_REGEX = re.compile(r"^(#+)\s+(.*)")

FRONT_MATTER_DELIMITER = "---"
METADATA_BLOCK_START = "::: {.metadata}"
CALLOUT_START = "::: {.callout-note"
BLOCK_END = ":::"
CODE_FENCE = "```"


@dataclass
class ParsedPart:
    project: str | None
    subject: str | None
    tags: list[str]
    lines: list[str]


@dataclass
class ParsedNote:
    file_date: str
    metadata: dict[str, str] = field(default_factory=dict)
    parts: list[ParsedPart] = field(default_factory=list)

    def as_dict(self) -> dict:
        """Représentation JSON historique (vue note_json, tests)."""
        return {
            "file date": self.file_date,
            "note metadata": self.metadata,
            "content": [
                {
                    "project": part.project,
                    "subject": part.subject,
                    "tags": part.tags,
                    "content": part.lines,
                }
                for part in self.parts
            ],
        }


@dataclass
class Level:
    """Niveau de titre : 1 = projet, 2 = sujet, 3 à 6 = tags."""

    title: str | None = None
    tags: set[str] | None = None


def parse_key_value(text: str) -> tuple[str, str]:
    parsed_text = text.split(":")
    if len(parsed_text) != 2:
        raise NoteParseError(
            f"La métadonnée est erronnée : format non type DICT ({text})"
        )
    return parsed_text[0].strip(), parsed_text[1].strip()


class NoteParser:
    def __init__(self, file_date: str):
        self.note = ParsedNote(file_date=file_date)
        self.levels = {level: Level() for level in range(1, MAX_LEVEL + 1)}
        self.current_level: int | None = None
        self.local_tags: set[str] = set()

        self.in_front_matter = False
        self.in_metadata_block = False
        self.in_callout = False
        self.in_code_block = False

    def parse(self, raw: str) -> ParsedNote:
        for number, line in enumerate(raw.split("\n")):
            self.parse_line(number, line.strip())
        self.clean_parts()
        return self.note

    # Lignes

    def parse_line(self, number: int, line: str) -> None:
        if not self.in_code_block and self.parse_block_delimiter(number, line):
            return

        if line.startswith(CODE_FENCE):
            self.in_code_block = not self.in_code_block

        if self.parse_title(line):
            return

        if self.in_front_matter and self.in_metadata_block:
            raise NoteParseError(
                "Erreur dans la lecture : à la fois block metadata local et global "
                f"(ligne numéro {number + 1} : {line})"
            )
        if self.in_front_matter and line != "":
            key, value = parse_key_value(line)
            self.note.metadata[key] = value
        elif self.in_metadata_block and line != "":
            self.parse_metadata_line(number, line)
        else:
            self.add_content(line)

    def parse_block_delimiter(self, number: int, line: str) -> bool:
        """Ouvre ou ferme un bloc ; renvoie True si la ligne est consommée."""
        if line == FRONT_MATTER_DELIMITER:
            self.in_front_matter = number == 0
        elif line == METADATA_BLOCK_START:
            self.in_metadata_block = True
        elif line.startswith(CALLOUT_START):
            self.in_callout = True
        elif self.in_metadata_block and line == BLOCK_END:
            self.in_metadata_block = False
        elif self.in_callout and line == BLOCK_END:
            self.in_callout = False
        else:
            return False
        return True

    def parse_title(self, line: str) -> bool:
        """Met à jour la hiérarchie ; renvoie True si la ligne est un titre."""
        match = TITLE_REGEX.match(line)
        if not match or self.in_code_block or self.in_callout:
            return False

        level = len(match.group(1))
        self.current_level = level
        if level > MAX_LEVEL:
            return True

        self.levels[level].title = match.group(2).strip()
        if level == 1:
            self.levels[1].tags = None
        for deeper in range(level + 1, MAX_LEVEL + 1):
            self.levels[deeper] = Level()
        return True

    def parse_metadata_line(self, number: int, line: str) -> None:
        key, value = parse_key_value(line)

        if key == "tags":
            if value[0] != "[" or value[-1] != "]":
                raise NoteParseError(
                    "La métadonnée locale est erronnée : format non type ARRAY "
                    f"(ligne numéro {number + 1} : {line})"
                )
            self.local_tags = {tag.strip() for tag in value.strip("[]").split(",")}

        if self.current_level is not None and self.current_level <= MAX_LEVEL:
            self.levels[self.current_level].tags = self.local_tags

    # Note parts

    def current_tags(self) -> set[str]:
        tags: set[str] = set()
        for level, state in self.levels.items():
            if level > 2 and state.title is not None:
                tags.add(state.title)
            if state.tags is not None:
                tags |= state.tags
        return tags

    def add_content(self, line: str) -> None:
        project = self.levels[1].title
        subject = self.levels[2].title
        tags = self.current_tags()

        for part in self.note.parts:
            if (part.project, part.subject, set(part.tags)) == (project, subject, tags):
                part.lines.append(line)
                return
        self.note.parts.append(ParsedPart(project, subject, list(tags), [line]))

    def clean_parts(self) -> None:
        """Retire les parts vides et les lignes vides en bordure."""
        self.note.parts = [
            part for part in self.note.parts if "".join(part.lines).strip() != ""
        ]
        for part in self.note.parts:
            while part.lines[0] == "":
                part.lines.pop(0)
            while part.lines[-1] == "":
                part.lines.pop()


def parse_note(file_date: str, raw: str) -> ParsedNote:
    return NoteParser(file_date).parse(raw)


def parse_note_raw_file_as_dict(date: str, raw: str) -> dict:
    """Analyse au format JSON historique ; voir ParsedNote.as_dict."""
    return parse_note(date, raw).as_dict()
