"""Un lien d'une note tel que rendu : dans un nouvel onglet (#438)."""

from note_taking.rendering.new_tab import HIDDEN_TEXT, ICON, NEW_TAB_ATTRS


def new_tab_link(href: str, text: str) -> str:
    return f'<a href="{href}"{NEW_TAB_ATTRS}>{text}{ICON}{HIDDEN_TEXT}</a>'
