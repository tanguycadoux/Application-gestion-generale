"""Liens d'une note vers d'autres notes (#206), sans accès à la base.

Un lien vers une note est un lien Markdown ordinaire, écrit dans l'application sans
extension : `[texte](AAAA-MM-JJ)` ou `[texte](AAAA-MM-JJ#ancre)`. Pour Pandoc, c'est
un lien relatif valide ; mais Quarto ne reconnaît une page du projet qu'à son fichier,
`AAAA-MM-JJ.qmd`, dont il fait un lien vers la page `.html` voisine. L'export ajoute
donc l'extension (`to_quarto`) et l'import la retire (`from_quarto`) : les fichiers
exportés sont un projet Quarto valide, et le texte de l'application reste court. La
forme avec `.qmd` est aussi lue partout. L'application fait mener le lien à la page
de la note (`rendering.note_links`) et garde qui cite qui (`PassageNoteLink`, #207).

La migration `0044_passagenotelink` en a une copie figée : la modifier ici ne la
change pas.
"""

import re
from dataclasses import dataclass
from datetime import date

# Lien (pas une image) vers une note, avec ou sans extension et un titre éventuel :
# [texte](2026-03-12#ancre "titre"), [texte](2026-03-12.qmd).
NOTE_LINK_REGEX = re.compile(
    r"(?<!!)\[[^\]\n]*\]\((?P<date>\d{4}-\d{2}-\d{2})(?P<extension>\.qmd)?"
    r"(?:#(?P<anchor>[^)\s\"]*))?(?:\s+\"[^\"\n]*\")?\)"
)
# Clôture d'un bloc de code (``` ou ~~~), et code en ligne.
FENCE_REGEX = re.compile(r"^\s*(`{3,}|~{3,})")
CODE_SPAN_REGEX = re.compile(r"`[^`\n]*`")


@dataclass(frozen=True)
class NoteLink:
    date: date
    # Identifiant d'un titre de la note citée, vide pour le haut de la note.
    anchor: str = ""


def without_code(text: str) -> str:
    """Le texte sans ses blocs ni ses morceaux de code : un lien écrit dans du code
    n'en est pas un."""
    kept, fence = [], None
    for line in text.splitlines():
        opening = FENCE_REGEX.match(line)
        if fence is not None:
            if opening and opening.group(1)[0] == fence:
                fence = None
            continue
        if opening:
            fence = opening.group(1)[0]
            continue
        kept.append(CODE_SPAN_REGEX.sub("", line))
    return "\n".join(kept)


def note_links(text: str) -> list[NoteLink]:
    """Les liens de ce texte vers d'autres notes, dans l'ordre, sans doublon.

    Une date qui n'existe pas (2026-13-45) n'est pas une note : ignorée.
    """
    found: dict[NoteLink, None] = {}
    for match in NOTE_LINK_REGEX.finditer(without_code(text)):
        try:
            day = date.fromisoformat(match.group("date"))
        except ValueError:
            continue
        found[NoteLink(day, match.group("anchor") or "")] = None
    return list(found)


def rewrite_outside_code(text: str, repl) -> str:
    """Applique `repl` aux liens vers des notes hors du code (blocs et code en ligne),
    sans toucher au reste du texte, fins de ligne comprises."""
    pieces, fence = [], None
    for line in text.splitlines(keepends=True):
        opening = FENCE_REGEX.match(line)
        if fence is not None:
            if opening and opening.group(1)[0] == fence:
                fence = None
            pieces.append(line)
            continue
        if opening:
            fence = opening.group(1)[0]
            pieces.append(line)
            continue
        position, kept = 0, []
        for span in CODE_SPAN_REGEX.finditer(line):
            kept.append(NOTE_LINK_REGEX.sub(repl, line[position : span.start()]))
            kept.append(span.group(0))
            position = span.end()
        kept.append(NOTE_LINK_REGEX.sub(repl, line[position:]))
        pieces.append("".join(kept))
    return "".join(pieces)


def with_extension(match: re.Match[str], extension: str) -> str:
    """Le lien trouvé, l'extension de sa date remplacée par `extension`."""
    start, end = match.span("date")
    if match.group("extension"):
        end = match.end("extension")
    offset = match.start()
    whole = match.group(0)
    return (
        whole[: start - offset]
        + match.group("date")
        + extension
        + whole[end - offset :]
    )


def to_quarto(text: str) -> str:
    """Les liens vers des notes avec l'extension `.qmd`, que Quarto suit (export)."""
    return rewrite_outside_code(text, lambda match: with_extension(match, ".qmd"))


def from_quarto(text: str) -> str:
    """Les liens vers des notes sans extension, comme on les écrit dans
    l'application (import d'un fichier qmd)."""
    return rewrite_outside_code(text, lambda match: with_extension(match, ""))
