"""Numérotation des tableaux et figures, et références croisées (#278)."""

import re

from .figures import FIGCAPTION_CLASSES

# Numérotation des tableaux et figures, comme Quarto (#278). Quarto 1.10.19 écrit
# « Table 1: » et « Figure 1: », même avec `lang: fr`.
FLOAT_LABELS = {"tbl": "Table", "fig": "Figure"}
NBSP = "\u00a0"
# Les balises qui ouvrent ou ferment une figure, une légende de figure, un tableau à
# légende ; une figure peut en contenir d'autres (images d'une figure en colonnes).
FLOAT_REGEX = re.compile(
    r"(?P<figure><figure(?P<figure_attrs>[^>]*)>)"
    r"|(?P<figure_end></figure>)"
    r"|(?P<figcaption><figcaption[^>]*>(?:<p>)?)"
    r"|(?P<table><table(?P<table_attrs>[^>]*)>\s*<caption>)"
)
ID_ATTR_REGEX = re.compile(r'\bid="(?P<id>(?:fig|tbl)-[\w-]+)"')
# Le texte à ne pas toucher : code, liens et balises ; le reste est du texte.
PROSE_SPLIT_REGEX = re.compile(
    r"(<pre\b.*?</pre>|<code\b.*?</code>|<a\b.*?</a>|<[^>]+>)", re.DOTALL
)
# « @fig-x » : pas collé à un mot ni à un autre « @ » (adresse électronique).
REFERENCE_REGEX = re.compile(r"(?<![\w@.])@(?P<id>(?:fig|tbl)-[\w-]*\w)")


def number_floats(html: str) -> str:
    """Numérote les tableaux et figures du HTML rendu, et relie les références.

    Les numéros repartent de 1 et suivent l'ordre du texte rendu (une note, ou
    un passage seul) : le même tableau n'a pas le même numéro dans les deux,
    écart assumé avec Quarto. Seuls comptent les tableaux à `{#tbl-…}` et à
    légende, et les figures à `{#fig-…}`, en colonnes ou à une seule image ; ce que
    contient une figure numérotée ne l'est pas. Une référence sans cible dans ce texte
    s'écrit comme dans Quarto, `?@id` en gras.
    """
    numbers: dict[str, str] = {}
    counters = {"tbl": 0, "fig": 0}
    # Figures ouvertes, de la plus haute à la plus profonde : le numéro à écrire dans
    # leur légende, vide pour une figure sans numéro ou dont la légende l'a déjà.
    figures: list[str] = []

    def label(float_id: str) -> str:
        kind = float_id[:3]
        counters[kind] += 1
        numbers[float_id] = f"{FLOAT_LABELS[kind]}{NBSP}{counters[kind]}"
        return numbers[float_id]

    def float_id(attrs: str, kind: str) -> str | None:
        found = ID_ATTR_REGEX.search(attrs)
        return found["id"] if found and found["id"].startswith(f"{kind}-") else None

    # Profondeur de la figure numérotée ouverte, 0 sans elle.
    depth_of_numbered = 0

    def number(match: re.Match[str]) -> str:
        nonlocal depth_of_numbered
        if match["figure"]:
            figure_id = float_id(match["figure_attrs"], "fig")
            numbered = depth_of_numbered == 0 and figure_id is not None
            figures.append(label(figure_id) if numbered and figure_id else "")
            if numbered:
                depth_of_numbered = len(figures)
            return match[0]
        if match["figcaption"]:
            if not figures or not figures[-1]:
                return match[0]
            text, figures[-1] = figures[-1], ""
            return f"{match[0]}{text}: "
        if match["figure_end"]:
            if not figures:
                return match[0]
            if depth_of_numbered == len(figures):
                depth_of_numbered = 0
            text = figures.pop()
            if not text:
                return match[0]
            # Sans légende, Quarto ne garde que « Figure N ».
            return (
                f'<figcaption class="{FIGCAPTION_CLASSES}">{text}</figcaption></figure>'
            )
        table_id = float_id(match["table_attrs"], "tbl")
        if depth_of_numbered or table_id is None:
            return match[0]
        return f"{match[0]}{label(table_id)}: "

    html = FLOAT_REGEX.sub(number, html)

    def reference(match: re.Match[str]) -> str:
        target = match.group("id")
        if target not in numbers:
            return f"<strong>?@{target}</strong>"
        return f'<a href="#{target}" class="quarto-xref">{numbers[target]}</a>'

    parts = PROSE_SPLIT_REGEX.split(html)
    for index in range(0, len(parts), 2):
        parts[index] = REFERENCE_REGEX.sub(reference, parts[index])
    return "".join(parts)
