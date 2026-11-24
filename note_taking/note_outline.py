"""Plan d'une note en lecture et sections repliables (#404).

Le HTML rendu d'une note (titres décalés, `#` en `h2`, avec leurs identifiants) devient :

- **des sections** : chaque titre du premier niveau du document ouvre une
  `<section class="note-section">` qui contient le titre puis son contenu dans
  `<div class="note-section-body">`, jusqu'au titre suivant de même niveau ou plus
  haut ; les sous-sections s'imbriquent. `note_reading.js` en fait des sections
  repliables. Un titre dans un bloc (encadré, citation) n'ouvre pas de section : elle
  en sortirait, et le HTML ne serait plus bien formé ;
- **le plan** : ces mêmes titres, avec leur niveau, leur texte et leur identifiant.

Rien n'est replié côté serveur : sans JavaScript, la note se lit en entier.
"""

import html as html_module
import re
from dataclasses import dataclass, field
from html.parser import HTMLParser

from .rendering import without_new_tab_marks

HEADING_REGEX = re.compile(
    r"<h(?P<level>[2-6])(?P<attrs>[^>]*)>(?P<inner>.*?)</h(?P=level)>", re.DOTALL
)
ID_REGEX = re.compile(r'\bid="(?P<id>[^"]*)"')
TAG_REGEX = re.compile(r"<[^>]*>")
VOID_ELEMENTS = {
    "area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta",
    "source", "track", "wbr",
}  # fmt: skip


# Retrait par niveau dans le plan, `h2` (le `#` de la note) d'abord ; écrit en entier
# pour que Tailwind trouve les classes.
INDENT = {2: "pl-2", 3: "pl-5", 4: "pl-8", 5: "pl-11", 6: "pl-14"}


@dataclass(frozen=True)
class OutlineEntry:
    level: int
    text: str
    id: str

    @property
    def indent(self) -> str:
        return INDENT[self.level]


@dataclass
class NoteLayout:
    html: str
    entries: list[OutlineEntry] = field(default_factory=list)


class TopLevelStarts(HTMLParser):
    """Les positions des balises ouvrantes du premier niveau du document."""

    def __init__(self, text: str) -> None:
        super().__init__(convert_charrefs=False)
        # `getpos` compte les lignes aux seuls « \n ».
        self.line_starts = [0]
        for line in text.split("\n"):
            self.line_starts.append(self.line_starts[-1] + len(line) + 1)
        self.depth = 0
        self.starts: set[int] = set()
        self.feed(text)
        self.close()

    def here(self) -> int:
        line, column = self.getpos()
        return self.line_starts[line - 1] + column

    def handle_starttag(self, tag, attrs):
        if self.depth == 0:
            self.starts.add(self.here())
        if tag not in VOID_ELEMENTS:
            self.depth += 1

    def handle_startendtag(self, tag, attrs):
        if self.depth == 0:
            self.starts.add(self.here())

    def handle_endtag(self, tag):
        if tag not in VOID_ELEMENTS:
            self.depth = max(0, self.depth - 1)


def outline_sections(html: str) -> NoteLayout:
    """Le HTML en sections imbriquées, et le plan de ses titres du premier niveau."""
    top = TopLevelStarts(html).starts
    pieces: list[str] = []
    entries: list[OutlineEntry] = []
    open_levels: list[int] = []
    position = 0
    for match in HEADING_REGEX.finditer(html):
        found = ID_REGEX.search(match["attrs"])
        if match.start() not in top or not found:
            continue
        level = int(match["level"])
        pieces.append(html[position : match.start()])
        while open_levels and open_levels[-1] >= level:
            open_levels.pop()
            pieces.append("</div></section>")
        open_levels.append(level)
        pieces.append(
            f'<section class="note-section" data-level="{level}">{match[0]}'
            f'<div class="note-section-body" id="section-body-{len(entries) + 1}">'
        )
        inner = without_new_tab_marks(match["inner"])
        text = html_module.unescape(TAG_REGEX.sub("", inner)).strip()
        entries.append(OutlineEntry(level, text, html_module.unescape(found["id"])))
        position = match.end()
    pieces.append(html[position:])
    pieces.extend("</div></section>" for _ in open_levels)
    return NoteLayout("".join(pieces), entries)
