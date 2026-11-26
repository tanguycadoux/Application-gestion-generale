"""Analyse du contenu d'une note qmd en passages (#387).

Une note est découpée selon ses titres :

- `#` : projet (la seule règle propre à l'application, #287) ;
- `##` à `######` : le chemin sous le projet, un niveau par titre, à
  n'importe quelle profondeur.

Des blocs `::: {.metadata}` donnent à la branche où ils sont écrits, sous-niveaux
compris, des tags (`tags: [a, b]`) et le marqueur de tâches (`todo: true`) : une
portée, jamais un niveau du chemin.

Un **passage** est une section telle qu'écrite : le texte entre un titre et le
suivant, ou depuis le début de la note, dans l'ordre, avec ses lignes de début et de
fin. Un titre répété donne deux passages ; un bloc `{.metadata}` écrit après du texte
en ouvre un nouveau, sous le même titre, pour que ses tags ne valent que pour la
suite. Le texte avant le premier `#` est un passage **sans projet** (#385), signalé
par un avertissement.

Une branche `todo: true` donne le tag `TODO` à ses passages : chaque élément de
liste y est une tâche, sans case (#297). Un titre `TODO` n'a plus de sens propre.
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
# Tag des passages d'une branche `todo: true` (#297).
TODO_TAG = "TODO"
# Attributs Pandoc en fin de titre, `{#id .classe clé=valeur}` : une écriture, pas
# un texte à lire (#356), ni une partie du nom du niveau (#367).
TITLE_ATTRIBUTES_REGEX = re.compile(r"\s*\{[^}]*\}\s*$")


def heading_name(title: str) -> str:
    """Le texte d'un titre, sans ses attributs : « Réunion {#reu-12} » donne
    « Réunion ». C'est le nom de son niveau (#367) et ce qu'affichent la note et les
    résultats. Un titre fait d'attributs seulement reste tel quel : sans nom, son
    niveau disparaîtrait du chemin."""
    return TITLE_ATTRIBUTES_REGEX.sub("", title).strip() or title.strip()


@dataclass
class ParsedPassage:
    # None pour le texte avant le premier `#` (#385).
    project: str | None
    # Titres de `##` à `######`, sans leurs attributs : les niveaux sous le projet
    # (#287, #367).
    path: list[str]
    tags: list[str]
    lines: list[str]
    # Titres de la section, du projet au plus profond (#240).
    headings: list[str] = field(default_factory=list)
    # Rang de chacun de ces titres parmi les titres de la note (`ParsedNote.headings`).
    heading_numbers: list[int] = field(default_factory=list)
    # Lignes du texte de la note, à partir de 1 : du titre (ou de la première ligne)
    # à la ligne qui précède le passage suivant.
    start_line: int = 1
    end_line: int = 1


@dataclass
class ParsedNote:
    file_date: str
    metadata: dict[str, str] = field(default_factory=dict)
    passages: list[ParsedPassage] = field(default_factory=list)
    # Les titres de la note, dans l'ordre, tels qu'écrits : ceux que le parseur
    # reconnaît (ni dans un bloc de code ni dans un callout, `#` à `######`).
    headings: list[str] = field(default_factory=list)
    # Pour chacun de ces titres : sa ligne (à partir de 1) et son niveau (#315).
    heading_lines: list[tuple[int, int]] = field(default_factory=list)
    # Ce qui est accepté mais probablement pas voulu : un titre qui saute un niveau,
    # un titre sans projet (#305). Le texte de la note n'est pas réécrit.
    warnings: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        """Représentation JSON historique (vue note_json, tests)."""
        return {
            "file date": self.file_date,
            "note metadata": self.metadata,
            "content": [
                {
                    "project": passage.project,
                    "path": passage.path,
                    "tags": passage.tags,
                    "content": passage.lines,
                }
                for passage in self.passages
            ],
        }


@dataclass
class Level:
    """Niveau de titre : 1 = projet, 2 à 6 = chemin sous le projet."""

    title: str | None = None
    # Rang du titre parmi les titres de la note.
    number: int | None = None
    tags: set[str] | None = None
    # `todo: true` ou `todo: false` du bloc de ce niveau ; None s'il n'en a pas.
    todo: bool | None = None


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
        # Numéro (à partir de 0) de la ligne en cours d'analyse.
        self.line_number = 0
        # Tous les passages, vides compris : leurs lignes se suivent sans trou.
        self.passages: list[ParsedPassage] = [ParsedPassage(None, [], [], [])]

    def parse(self, raw: str) -> ParsedNote:
        lines = raw.split("\n")
        for number, raw_line in enumerate(lines):
            self.line_number = number
            # Détection sur la ligne sans espaces ; contenu avec son indentation.
            line = raw_line.strip()
            self.parse_line(number, line, raw_line.rstrip())
            if line != "":
                self.front_matter_allowed = False
        self.close_passages(len(lines))
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

        if self.parse_title(number, line):
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

    def parse_title(self, number: int, line: str) -> bool:
        """Met à jour la hiérarchie ; renvoie True si la ligne est un titre."""
        match = TITLE_REGEX.match(line)
        if not match or self.in_code_block or self.in_callout:
            return False

        level = len(match.group(1))
        self.current_level = level
        if level > MAX_LEVEL:
            return True
        self.check_level(number + 1, level, match.group(2).strip())

        # Un nouveau titre remplace son niveau et efface les niveaux plus profonds.
        title = match.group(2).strip()
        self.levels[level] = Level(title=title, number=len(self.note.headings))
        self.note.headings.append(title)
        self.note.heading_lines.append((number + 1, level))
        for deeper in range(level + 1, MAX_LEVEL + 1):
            self.levels[deeper] = Level()
        # Le titre ouvre un passage.
        self.passages.append(self.new_passage(number + 1))
        return True

    def check_level(self, number: int, level: int, title: str) -> None:
        """Signale un titre sans projet au-dessus, ou qui saute un niveau (#305) :
        accepté tel quel, le chemin se fait des titres et pas de leur niveau."""
        hashes = "#" * level
        if self.levels[1].title is None:
            if level > 1:
                self.note.warnings.append(
                    f"Ligne {number} : le titre « {title} » ({hashes}) n'a pas de "
                    "projet (#) au-dessus de lui : son contenu est gardé sans projet."
                )
            return
        deepest = max(
            current for current, state in self.levels.items() if state.title is not None
        )
        if level > deepest + 1:
            self.note.warnings.append(
                f"Ligne {number} : le titre « {title} » ({hashes}) saute un niveau "
                f"sous « {self.levels[deepest].title} » ({'#' * deepest})."
            )

    def parse_metadata_line(self, number: int, line: str) -> None:
        key, value = parse_key_value(line, number + 1)
        level = self.current_level
        # Un bloc avant tout titre, ou sous un titre au-delà de `######`, ne vaut pour rien.
        state = self.levels[level] if level is not None and level <= MAX_LEVEL else None

        if key == "tags":
            if not value.startswith("[") or not value.endswith("]"):
                raise NoteParseError(
                    f"Ligne {number + 1} : les tags s'écrivent entre crochets, "
                    "par exemple « tags: [a, b] »."
                )
            tags = (tag.strip() for tag in value.strip("[]").split(","))
            self.local_tags = {tag for tag in tags if tag}
            if state is not None:
                state.tags = self.local_tags
        elif key == "todo":
            if value not in ("true", "false"):
                raise NoteParseError(
                    f"Ligne {number + 1} : « todo » vaut « true » ou « false », "
                    "par exemple « todo: true »."
                )
            if state is not None:
                state.todo = value == "true"

    # Passages

    def current_path(self) -> list[str]:
        """Les niveaux sous le projet : le texte des titres, sans attributs (#367)."""
        return [
            heading_name(state.title)
            for level, state in self.levels.items()
            if level > 1 and state.title is not None
        ]

    def is_todo(self) -> bool:
        """La branche est marquée `todo: true` ; le niveau le plus profond qui en
        parle l'emporte (`todo: false` retire le marqueur d'un niveau parent)."""
        for state in reversed(list(self.levels.values())):
            if state.todo is not None:
                return state.todo
        return False

    def current_tags(self) -> set[str]:
        tags: set[str] = set()
        for state in self.levels.values():
            if state.tags is not None:
                tags |= state.tags
        if self.is_todo():
            tags.add(TODO_TAG)
        return tags

    def new_passage(self, start_line: int) -> ParsedPassage:
        """Un passage vide sous les titres en cours, à partir de cette ligne."""
        titled = [state for state in self.levels.values() if state.title is not None]
        return ParsedPassage(
            project=self.levels[1].title,
            path=self.current_path(),
            tags=sorted(self.current_tags()),
            lines=[],
            headings=[state.title for state in titled if state.title is not None],
            heading_numbers=[
                state.number for state in titled if state.number is not None
            ],
            start_line=start_line,
        )

    def add_content(self, line: str) -> None:
        passage = self.passages[-1]
        tags = sorted(self.current_tags())
        if passage.tags != tags:
            if any(text.strip() for text in passage.lines):
                # Un bloc `{.metadata}` après du texte : ses tags valent pour la
                # suite seulement, dans un nouveau passage sous le même titre.
                passage = self.new_passage(self.line_number + 1)
                self.passages.append(passage)
            passage.tags = tags
        passage.lines.append(line)

    def close_passages(self, line_count: int) -> None:
        """Pose la ligne de fin de chaque passage, retire les passages vides et les
        lignes vides en bordure, et signale le texte sans projet (#385)."""
        for passage, following in zip(self.passages, self.passages[1:], strict=False):
            passage.end_line = following.start_line - 1
        self.passages[-1].end_line = line_count
        kept = [
            passage for passage in self.passages if "".join(passage.lines).strip() != ""
        ]
        for passage in kept:
            while passage.lines[0] == "":
                passage.lines.pop(0)
            while passage.lines[-1] == "":
                passage.lines.pop()
        self.note.passages = kept

        unfiled = sum(
            1
            for passage in kept
            if passage.project is None
            for text in passage.lines
            if text.strip()
        )
        if unfiled:
            lines = "1 ligne" if unfiled == 1 else f"{unfiled} lignes"
            # En tête : le message de l'enregistrement ne dit que le premier.
            self.note.warnings.insert(
                0,
                f"{lines} sans projet, avant le premier titre « # » : à ranger "
                "sous un projet.",
            )


def parse_note(file_date: str, raw: str) -> ParsedNote:
    return NoteParser(file_date).parse(raw)


def parse_note_raw_file_as_dict(date: str, raw: str) -> dict:
    """Analyse au format JSON historique ; voir ParsedNote.as_dict."""
    return parse_note(date, raw).as_dict()
