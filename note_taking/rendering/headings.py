"""Titres du HTML rendu : décalage de niveau et identifiants (#201)."""

import html as html_module
import re

from django.utils.html import escape

from .markdown import render_plain_markdown

# Balise de titre ouvrante ou fermante du HTML rendu : <h2 …> ou </h2>.
HEADING_TAG_REGEX = re.compile(r"<(?P<slash>/?)h(?P<level>[1-6])\b")


HEADING_BLOCK_REGEX = re.compile(
    r"<h(?P<level>[1-6])(?P<attrs>[^>]*)>(?P<inner>.*?)</h(?P=level)>", re.DOTALL
)
ANY_ID_REGEX = re.compile(r'\bid="(?P<id>[^"]*)"')
HTML_TAG_REGEX = re.compile(r"<[^>]*>")
FIRST_LETTER_REGEX = re.compile(r"[^\W\d_]")


def heading_slug(text: str) -> str:
    """Identifiant automatique d'un titre, comme Pandoc : minuscules, rien d'autre
    que lettres, chiffres, `_`, `-` et `.`, espaces en tirets, tout ce qui précède la
    première lettre retiré ; « section » s'il ne reste rien."""
    text = re.sub(r"[^\w\s.-]", "", text.casefold())
    text = "-".join(text.split())
    letter = FIRST_LETTER_REGEX.search(text)
    return text[letter.start() :] if letter else "section"


def add_heading_ids(html: str) -> str:
    """Donne un `id` à chaque titre qui n'en a pas (`{#id}` est conservé).

    Les titres répétés prennent `-1`, `-2`… comme dans Pandoc ; un identifiant déjà
    pris dans la page (figure, tableau) compte aussi.
    """
    used = {match["id"] for match in ANY_ID_REGEX.finditer(html)}

    def add(match: re.Match[str]) -> str:
        if ANY_ID_REGEX.search(match["attrs"]):
            return match[0]
        text = html_module.unescape(HTML_TAG_REGEX.sub("", match["inner"]))
        slug = candidate = heading_slug(text)
        count = 0
        while candidate in used:
            count += 1
            candidate = f"{slug}-{count}"
        used.add(candidate)
        return (
            f'<h{match["level"]}{match["attrs"]} id="{escape(candidate)}">'
            f"{match['inner']}</h{match['level']}>"
        )

    return HEADING_BLOCK_REGEX.sub(add, html)


def heading_anchor(title: str) -> str | None:
    """L'identifiant que prend ce titre, tel qu'écrit, dans la page d'une note.

    Un titre répété dans la note a un identifiant numéroté que ce titre seul ne
    permet pas de connaître : c'est celui de la première occurrence.
    """
    if not title.strip():
        return None
    html = add_heading_ids(render_plain_markdown("# " + title))
    heading = HEADING_BLOCK_REGEX.search(html)
    found = ANY_ID_REGEX.search(heading["attrs"]) if heading else None
    return found["id"] if found else None


def shift_heading(match: re.Match[str]) -> str:
    level = min(int(match.group("level")) + 1, 6)
    return f"<{match.group('slash')}h{level}"
