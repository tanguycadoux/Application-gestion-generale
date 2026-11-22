"""Numérotation des tableaux et figures, et références croisées (#278)."""

import re

# Numérotation des tableaux et figures, comme Quarto (#278). Quarto 1.10.19 écrit
# « Table 1: » et « Figure 1: », même avec `lang: fr`.
FLOAT_LABELS = {"tbl": "Table", "fig": "Figure"}
NBSP = "\u00a0"
FLOAT_REGEX = re.compile(
    r'(?P<layout><figure class="my-2" id="(?P<layout_id>fig-[\w-]+)">.*?</figure>)'
    r"|(?P<table><table(?P<table_attrs>[^>]*)>\s*<caption>)"
    r"|<p>(?P<image><img [^>]*>)</p>",
    re.DOTALL,
)
FIGCAPTION_OPEN_REGEX = re.compile(r"<figcaption[^>]*>(?:<p>)?")
ID_ATTR_REGEX = re.compile(r'\bid="(?P<id>(?:fig|tbl)-[\w-]+)"')
ALT_ATTR_REGEX = re.compile(r'\balt="(?P<alt>[^"]*)"')
FIGCAPTION_CLASSES = "mt-2 text-sm text-center text-slate-600"
# Le texte à ne pas toucher : code, liens et balises ; le reste est du texte.
PROSE_SPLIT_REGEX = re.compile(
    r"(<pre\b.*?</pre>|<code\b.*?</code>|<a\b.*?</a>|<[^>]+>)", re.DOTALL
)
# « @fig-x » : pas collé à un mot ni à un autre « @ » (adresse électronique).
REFERENCE_REGEX = re.compile(r"(?<![\w@.])@(?P<id>(?:fig|tbl)-[\w-]*\w)")


def number_floats(html: str) -> str:
    """Numérote les tableaux et figures du HTML rendu, et relie les références.

    Les numéros repartent de 1 et suivent l'ordre du texte rendu (une note, ou
    une note part seule) : le même tableau n'a pas le même numéro dans les deux,
    écart assumé avec Quarto. Seuls comptent les tableaux à `{#tbl-…}` et à
    légende, et les figures à `{#fig-…}` et à légende : une image seule devient
    une `<figure>`, comme dans Quarto. Une référence sans cible dans ce texte
    s'écrit comme dans Quarto, `?@id` en gras.
    """
    numbers: dict[str, str] = {}
    counters = {"tbl": 0, "fig": 0}

    def label(float_id: str) -> str:
        kind = float_id[:3]
        counters[kind] += 1
        numbers[float_id] = f"{FLOAT_LABELS[kind]}{NBSP}{counters[kind]}"
        return numbers[float_id]

    def number(match: re.Match[str]) -> str:
        if match.group("layout"):
            figure = match.group("layout")
            number_text = label(match.group("layout_id"))
            caption = FIGCAPTION_OPEN_REGEX.search(figure)
            if caption is None:
                # Sans légende, Quarto ne garde que « Figure N ».
                return (
                    figure.removesuffix("</figure>")
                    + f'<figcaption class="{FIGCAPTION_CLASSES}">{number_text}'
                    "</figcaption></figure>"
                )
            return (
                figure[: caption.end()] + f"{number_text}: " + figure[caption.end() :]
            )
        if match.group("table"):
            id_attr = ID_ATTR_REGEX.search(match.group("table_attrs"))
            if id_attr is None or id_attr.group("id").startswith("fig-"):
                return match.group(0)
            return f"{match.group(0)}{label(id_attr.group('id'))}: "
        image = match.group("image")
        id_attr = ID_ATTR_REGEX.search(image)
        alt = ALT_ATTR_REGEX.search(image)
        if id_attr is None or not id_attr.group("id").startswith("fig-"):
            return match.group(0)
        figure_id = id_attr.group("id")
        text = alt.group("alt") if alt else ""
        image = image.replace(id_attr.group(0), "", 1).replace(" >", ">")
        image = re.sub(r"\s{2,}", " ", image)
        return (
            f'<figure class="my-2" id="{figure_id}">{image}'
            f'<figcaption class="{FIGCAPTION_CLASSES}">'
            f"{label(figure_id)}{': ' + text if text else ''}</figcaption></figure>"
        )

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
