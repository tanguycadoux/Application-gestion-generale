"""Liens d'une note ouverts dans un nouvel onglet (#438), pour ne pas la quitter."""

import re

# Lien du HTML filtré, qui n'en contient pas d'autre ; une valeur d'attribut peut
# contenir « > ».
LINK_REGEX = re.compile(
    r'<a(?P<attrs>(?:\s+[\w-]+="[^"]*")*)>(?P<inner>.*?)</a>', re.DOTALL
)
HREF_REGEX = re.compile(r'\shref="(?P<href>[^"]*)"')
TAG_REGEX = re.compile(r"<[^>]*>")

NEW_TAB_ATTRS = ' target="_blank" rel="noopener noreferrer"'
# Flèche collée au dernier mot par une espace fine insécable, en texte et non en emoji
# (U+FE0E). Le texte masqué est positionné : sans `relative`, il allongerait la page.
ICON = '<span class="select-none print:hidden" aria-hidden="true"> ↗︎</span>'
HIDDEN_TEXT = (
    '<span class="relative"><span class="sr-only"> (nouvel onglet)</span></span>'
)


def open_links_in_new_tab(html: str) -> str:
    """Les liens qui quittent la page s'ouvrent dans un nouvel onglet, et le disent.

    Le HTML est filtré : il ne porte aucun `target` ni `rel` écrit dans la note. Une
    ancre (`#…`) ou un renvoi vers une figure reste dans la page. Une image seule dans
    son lien n'a pas de flèche.
    """
    return LINK_REGEX.sub(mark, html)


def mark(match: re.Match[str]) -> str:
    href = HREF_REGEX.search(match["attrs"])
    if href is None or not href["href"] or href["href"].startswith("#"):
        return match[0]
    inner = match["inner"]
    only_image = "<img" in inner and not TAG_REGEX.sub("", inner).strip()
    icon = "" if only_image else ICON
    return f"<a{match['attrs']}{NEW_TAB_ATTRS}>{inner}{icon}{HIDDEN_TEXT}</a>"


def without_new_tab_marks(html: str) -> str:
    """Sans flèche ni texte masqué, pour lire le texte d'un titre qui a un lien."""
    return html.replace(ICON, "").replace(HIDDEN_TEXT, "")
