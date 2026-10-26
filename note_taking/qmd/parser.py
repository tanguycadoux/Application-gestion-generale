"""Analyse du contenu d'une note qmd en note parts.

Une note est découpée selon ses titres :

- `#` : projet (la seule règle propre à l'application, #287) ;
- `##` à `######` : le chemin sous le projet, un niveau par titre, à
  n'importe quelle profondeur.

Des blocs `::: {.metadata}` ajoutent des tags à la branche où ils sont écrits,
sous-niveaux compris : une portée, jamais un niveau du chemin. Le texte
partageant le même projet, le même chemin et les mêmes tags forme une note part.

Le titre `TODO` (de `###` à `######`) marque une section de tâches : il n'entre
pas dans le chemin, et la note part reçoit le tag `TODO` (#297 le remplace par
les cases à cocher).
"""

import re
from dataclasses import dataclass, field

from ..exceptions import NoteParseError

MAX_LEVEL = 6

TITLE_REGEX = re.compile(r"^(#+)\s+(.*)")

FRONT_MATTER_DELIMITER = "---"
METADATA_BLOCK_START = "::: {.metadata}"
CALLOUT_START = "::: {.callout-"
BLOCK_END = ":::"
CODE_FENCE = "```"
# Séparateur des titres d'une section, du projet au plus profond (#240).
HEADING_SEPARATOR = " › "
# Titre qui marque une section de tâches, de `###` à `######` (#297).
TODO_TITLE = "TODO"


@dataclass
class ParsedPart:
    project: str | None
    # Titres de `##` à `######`, sans `TODO` : les niveaux sous le projet (#287).
    path: list[str]
    tags: list[str]
    lines: list[str]
    # Titres de la section de sa première ligne, du projet au plus profond (#240).
    headings: list[str] = field(default_factory=list)


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
                    "path": part.path,
                    "tags": part.tags,
                    "content": part.lines,
                }
                for part in self.parts
            ],
        }


@dataclass
class Level:
    """Niveau de titre : 1 = projet, 2 à 6 = chemin sous le projet."""

    title: str | None = None
    tags: set[str] | None = None


def parse_key_value(text: str, line_number: int) -> tuple[str, str]:
    # Découpage sur le premier « : » seulement : la valeur peut en contenir.
    parsed_text = text.split(":", 1)
    if len(parsed_text) != 2:
        raise NoteParseError(
            f"Ligne {line_number} : métadonnée invalide (« {text} »), "
            "la forme attendue est « clé: valeur »."
        )
    return parsed_text[0].strip(), parsed_text[1].strip()


class NoteParser:
    def __init__(self, file_date: str):
        self.note = ParsedNote(file_date=file_date)
        self.levels = {level: Level() for level in range(1, MAX_LEVEL + 1)}
        self.current_level: int | None = None
        self.local_tags: set[str] = set()

        self.in_front_matter = False
        # Le bloc d'en-tête ne peut commencer qu'avant toute ligne non vide.
        self.front_matter_allowed = True
        self.in_metadata_block = False
        self.in_callout = False
        self.in_code_block = False

    def parse(self, raw: str) -> ParsedNote:
        for number, raw_line in enumerate(raw.split("\n")):
            # Détection sur la ligne sans espaces ; contenu avec son indentation.
            line = raw_line.strip()
            self.parse_line(number, line, raw_line.rstrip())
            if line != "":
                self.front_matter_allowed = False
        self.clean_parts()
        return self.note

    # Lignes

    def parse_line(self, number: int, line: str, content: str) -> None:
        if not self.in_code_block and self.parse_block_delimiter(number, line):
            return

        if not self.in_code_block and self.parse_callout_delimiter(line):
            # Les marqueurs de callout restent dans le contenu, pour le rendu.
            self.add_content(content)
            return

        if line.startswith(CODE_FENCE):
            self.in_code_block = not self.in_code_block

        if self.parse_title(line):
            return

        if self.in_front_matter and self.in_metadata_block:
            raise NoteParseError(
                f"Ligne {number + 1} : bloc de métadonnées ouvert dans le bloc "
                "d'en-tête, à fermer d'abord (ligne ---)."
            )
        if self.in_front_matter and line != "":
            key, value = parse_key_value(line, number + 1)
            self.note.metadata[key] = value
        elif self.in_metadata_block and line != "":
            self.parse_metadata_line(number, line)
        else:
            self.add_content(content)

    def parse_block_delimiter(self, number: int, line: str) -> bool:
        """Ouvre ou ferme un bloc ; renvoie True si la ligne est consommée."""
        if line == FRONT_MATTER_DELIMITER and self.in_front_matter:
            self.in_front_matter = False
        elif line == FRONT_MATTER_DELIMITER and self.front_matter_allowed:
            self.in_front_matter = True
        elif line == METADATA_BLOCK_START:
            self.in_metadata_block = True
        elif self.in_metadata_block and line == BLOCK_END:
            self.in_metadata_block = False
        else:
            return False
        return True

    def parse_callout_delimiter(self, line: str) -> bool:
        """Ouvre ou ferme un callout ; renvoie True si la ligne est un marqueur."""
        if line.startswith(CALLOUT_START):
            self.in_callout = True
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

        # Un nouveau titre remplace son niveau et efface les niveaux plus profonds.
        self.levels[level] = Level(title=match.group(2).strip())
        for deeper in range(level + 1, MAX_LEVEL + 1):
            self.levels[deeper] = Level()
        return True

    def parse_metadata_line(self, number: int, line: str) -> None:
        key, value = parse_key_value(line, number + 1)

        if key == "tags":
            if not value.startswith("[") or not value.endswith("]"):
                raise NoteParseError(
                    f"Ligne {number + 1} : les tags s'écrivent entre crochets, "
                    "par exemple « tags: [a, b] »."
                )
            tags = (tag.strip() for tag in value.strip("[]").split(","))
            self.local_tags = {tag for tag in tags if tag}

        if self.current_level is not None and self.current_level <= MAX_LEVEL:
            self.levels[self.current_level].tags = self.local_tags

    # Note parts

    def is_todo_marker(self, level: int, state: Level) -> bool:
        return level > 2 and state.title == TODO_TITLE

    def current_path(self) -> list[str]:
        return [
            state.title
            for level, state in self.levels.items()
            if level > 1
            and state.title is not None
            and not self.is_todo_marker(level, state)
        ]

    def current_tags(self) -> set[str]:
        tags: set[str] = set()
        for level, state in self.levels.items():
            if self.is_todo_marker(level, state):
                tags.add(TODO_TITLE)
            if state.tags is not None:
                tags |= state.tags
        return tags

    def add_content(self, line: str) -> None:
        project = self.levels[1].title
        if project is None:
            # Texte avant le premier projet : ignoré pour l'instant (#36).
            return
        path = self.current_path()
        tags = self.current_tags()

        for part in self.note.parts:
            if (part.project, part.path, set(part.tags)) == (project, path, tags):
                part.lines.append(line)
                return
        headings = [
            state.title for state in self.levels.values() if state.title is not None
        ]
        self.note.parts.append(ParsedPart(project, path, list(tags), [line], headings))

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
