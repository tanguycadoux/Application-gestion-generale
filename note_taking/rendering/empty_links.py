"""Un lien sans texte affiche son adresse (#467), écart voulu à Pandoc : vide, il ne se
verrait pas et ne pourrait pas être suivi."""

import html as html_module
import re

from django.utils.html import escape

from core.dates import date_text

from .headings import add_heading_ids, heading_texts
from .new_tab import HREF_REGEX, LINK_REGEX, TAG_REGEX
from .note_links import NOTE_HREF_REGEX, parse_day


def is_empty(inner: str) -> bool:
    """Ni texte (des espaces, insécables compris, n'en sont pas un) ni image."""
    return (
        "<img" not in inner
        and not html_module.unescape(TAG_REGEX.sub("", inner)).strip()
    )


def fill_empty_links(html: str, heading_prefix: str = "") -> str:
    """Donne un texte aux liens qui n'en ont pas.

    Appliqué au HTML filtré, après les identifiants des titres, où ce texte n'entre donc
    pas, et avant que les liens vers des notes ne mènent à leur page. `heading_prefix`
    est celui des identifiants, que les ancres écrites n'ont pas.
    """
    titles: dict[str, str] | None = None

    def fill(match: re.Match[str]) -> str:
        nonlocal titles
        found = HREF_REGEX.search(match["attrs"])
        if found is None or not found["href"] or not is_empty(match["inner"]):
            return match[0]
        href = html_module.unescape(found["href"])
        text = href.removeprefix("mailto:")
        if href.startswith("#"):
            if titles is None:
                # Un texte peut venir sans identifiants : ceux qu'il aurait dans sa page.
                titles = {
                    anchor.removeprefix(heading_prefix): title
                    for title, anchor in heading_texts(add_heading_ids(html))
                }
            text = titles.get(href[1:]) or href
        elif note := NOTE_HREF_REGEX.fullmatch(href):
            day = parse_day(note["date"])
            text = f"Note du {date_text(day, 'long')}" if day else note["date"]
        return f"<a{match['attrs']}>{escape(text)}</a>"

    return LINK_REGEX.sub(fill, html)
