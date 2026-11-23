"""Liens d'une note vers d'autres notes (#206), sans accès à la base.

Un lien vers une note est un lien Markdown ordinaire vers son fichier :
`[texte](AAAA-MM-JJ.qmd)` ou `[texte](AAAA-MM-JJ.qmd#ancre)`. Quarto en fait un lien
vers la page `.html` voisine, et l'export met les notes à la racine : le lien marche
tel quel une fois exporté. L'application le fait mener à la page de la note
(`rendering.note_links`) et garde qui cite qui (`PassageNoteLink`, #207).

La migration `0044_passagenotelink` en a une copie figée : la modifier ici ne la
change pas.
"""

import re
from dataclasses import dataclass
from datetime import date

# Lien (pas une image) vers le fichier d'une note, avec un titre éventuel :
# [texte](2026-03-12.qmd#ancre "titre").
NOTE_LINK_REGEX = re.compile(
    r"(?<!!)\[[^\]\n]*\]\((?P<date>\d{4}-\d{2}-\d{2})\.qmd"
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
