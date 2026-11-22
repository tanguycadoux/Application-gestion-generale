"""Markdown avec blocs Quarto : callouts, figures en colonnes, colonnes, métadonnées.

Les blocs se rendent les uns dans les autres : `render_markdown` et le rendu
de chaque bloc s'appellent mutuellement, d'où un seul module."""

import re

from django.utils.html import escape

from core.icons import icon_svg

from ..qmd.parser import METADATA_BLOCK_START, TODO_TAG
from .divs import CODE_FENCE, DIV_ID_REGEX, find_block_end, split_blocks
from .markdown import render_plain_markdown

# Callout Quarto : ::: {.callout-<type> title="…"} … :::
CALLOUT_START_REGEX = re.compile(r"^:::\s*\{\.callout-(?P<type>\w+)(?P<attrs>[^}]*)\}$")
CALLOUT_TITLE_ATTR_REGEX = re.compile(r'title="(?P<title>[^"]*)"')
CALLOUT_HEADING_REGEX = re.compile(r"^#+\s+(?P<title>.+)$")

# Bloc de métadonnées maison : ::: {.metadata} … ::: (tags, todo), affiché en pastilles
METADATA_START_REGEX = re.compile("^" + re.escape(METADATA_BLOCK_START) + "$")
TAG_CLASSES = (
    "rounded-2xl border border-slate-300 bg-slate-200 px-[.4rem] py-[.1rem] "
    "text-[.8rem] font-semibold"
)


# Figure en colonnes : ::: {#fig-… layout-ncol=N} … légende :::
LAYOUT_START_REGEX = re.compile(
    r"^:::\s*\{(?P<attrs>[^}]*\blayout-ncol=(?P<ncol>\d+)[^}]*)\}$"
)
# Classes Tailwind écrites en entier, pour qu'un build puisse les détecter.
LAYOUT_GRID_CLASSES = {
    1: "grid-cols-1",
    2: "grid-cols-2",
    3: "grid-cols-3",
    4: "grid-cols-4",
    5: "grid-cols-5",
    6: "grid-cols-6",
}

# Colonnes : ::: {.columns} ::: {.column width="40%"} … ::: :::
COLUMNS_START_REGEX = re.compile(r"^:::\s*\{\.columns\}$")
COLUMN_START_REGEX = re.compile(r"^:::\s*\{\.column(?P<attrs>[^}]*)\}$")
COLUMN_WIDTH_REGEX = re.compile(r'width="?(?P<width>\d+(?:\.\d+)?%)"?')

# Titres par défaut de Quarto en français
CALLOUT_DEFAULT_TITLES = {
    "note": "Note",
    "tip": "Astuce",
    "warning": "Avertissement",
    "caution": "Attention",
    "important": "Important",
}

# Icônes Material Symbols proches de celles de Quarto
CALLOUT_ICONS = {
    "note": "info",
    "tip": "lightbulb",
    "warning": "warning",
    "caution": "report",
    "important": "error",
}
CALLOUT_NO_ICON_ATTR_REGEX = re.compile(r"\bicon=false\b")


def render_markdown(text: str) -> str:
    """Rend du Markdown en HTML, callouts et blocs de mise en page Quarto compris."""
    html: list[str] = []
    pending: list[str] = []
    lines = text.split("\n")
    in_code_block = False
    index = 0

    while index < len(lines):
        line = lines[index]
        stripped = line.strip()
        if stripped.startswith(CODE_FENCE):
            in_code_block = not in_code_block

        block = None if in_code_block else match_block_start(stripped)
        end = find_block_end(lines, index) if block else None
        if block and end is not None:
            start, render_block = block
            html.append(render_plain_markdown("\n".join(pending)))
            pending = []
            html.append(render_block(start, lines[index + 1 : end]))
            index = end + 1
            continue

        pending.append(line)
        index += 1

    html.append(render_plain_markdown("\n".join(pending)))
    return "\n".join(part for part in html if part)


def match_block_start(line: str):
    """Début de bloc rendu à part (callout, figure, colonnes) et son rendu."""
    for regex, render_block in (
        (CALLOUT_START_REGEX, render_callout),
        (LAYOUT_START_REGEX, render_layout),
        (COLUMNS_START_REGEX, render_columns),
        (METADATA_START_REGEX, render_metadata),
    ):
        start = regex.match(line)
        if start:
            return start, render_block
    return None


def render_layout(start: re.Match[str], body: list[str]) -> str:
    """Blocs disposés en grille de N colonnes, à la manière de Quarto.

    Avec un identifiant `#fig-…`, le bloc est une figure et son dernier
    paragraphe, s'il n'est pas une image, en est la légende commune.
    """
    attrs = start.group("attrs")
    id_match = DIV_ID_REGEX.search(attrs)
    block_id = id_match.group("id") if id_match else None
    is_figure = bool(block_id and block_id.startswith("fig-"))

    cells = split_blocks(body)
    caption = None
    if is_figure and len(cells) > 1 and not cells[-1].lstrip().startswith("!["):
        caption = cells.pop()

    ncol = min(max(int(start.group("ncol")), 1), max(LAYOUT_GRID_CLASSES))
    tag = "figure" if is_figure else "div"
    id_attr = f' id="{escape(block_id)}"' if block_id else ""
    cells_html = "".join(
        f'<div class="min-w-0">{render_markdown(cell)}</div>' for cell in cells
    )
    caption_html = (
        '<figcaption class="mt-2 text-sm text-center text-slate-600">'
        f"{render_markdown(caption)}</figcaption>"
        if caption is not None
        else ""
    )

    return (
        f'<{tag} class="my-2"{id_attr}>'
        f'<div class="grid {LAYOUT_GRID_CLASSES[ncol]} gap-4 items-start">'
        f"{cells_html}</div>{caption_html}</{tag}>"
    )


def render_columns(start: re.Match[str], body: list[str]) -> str:
    """Colonnes côte à côte ; une colonne sans largeur occupe la place restante."""
    columns: list[tuple[str, list[str]]] = []
    stray: list[str] = []
    index = 0
    while index < len(body):
        column = COLUMN_START_REGEX.match(body[index].strip())
        end = find_block_end(body, index) if column else None
        if column and end is not None:
            if "".join(stray).strip():
                columns.append(("", stray))
            stray = []
            columns.append((column.group("attrs"), body[index + 1 : end]))
            index = end + 1
            continue
        stray.append(body[index])
        index += 1
    if "".join(stray).strip():
        columns.append(("", stray))

    columns_html = []
    for attrs, lines in columns:
        width = COLUMN_WIDTH_REGEX.search(attrs)
        opening = (
            f'<div class="min-w-0" style="flex: 0 1 {width.group("width")}">'
            if width
            else '<div class="flex-1 min-w-0">'
        )
        columns_html.append(f"{opening}{render_markdown('\n'.join(lines))}</div>")

    return f'<div class="flex gap-4 my-2">{"".join(columns_html)}</div>'


def render_metadata(start: re.Match[str], body: list[str]) -> str:
    """Les tags d'un bloc `{.metadata}` en pastilles, comme ceux d'un passage.

    `todo: true` s'affiche comme le tag `TODO` que ses passages reçoivent.
    Une autre clé, ou une ligne mal écrite, n'est pas affichée : l'analyse
    la signale à l'enregistrement.
    """
    tags: list[str] = []
    for line in body:
        key, _, value = line.partition(":")
        value = value.strip()
        if key.strip() == "tags" and value.startswith("[") and value.endswith("]"):
            tags += [tag.strip() for tag in value[1:-1].split(",") if tag.strip()]
        elif key.strip() == "todo" and value == "true":
            tags.append(TODO_TAG)
    if not tags:
        return ""
    items = "".join(f'<li class="{TAG_CLASSES}">{escape(tag)}</li>' for tag in tags)
    return (
        '<ul class="note-tags m-0 my-2 flex list-none flex-wrap gap-[.4rem] p-0">'
        f"{items}</ul>"
    )


def render_callout(start: re.Match[str], body: list[str]) -> str:
    """Encadré à la manière de Quarto.

    Le titre est l'attribut `title`, sinon le premier titre Markdown du
    callout, sinon le titre par défaut du type. L'icône dépend du type et
    se retire avec `icon=false`.
    """
    callout_type = start.group("type")
    attrs = start.group("attrs")
    title_attr = CALLOUT_TITLE_ATTR_REGEX.search(attrs)
    body = list(body)

    if title_attr:
        title = title_attr.group("title")
    else:
        first = next((i for i, line in enumerate(body) if line.strip()), None)
        heading = (
            CALLOUT_HEADING_REGEX.match(body[first].strip())
            if first is not None
            else None
        )
        if first is not None and heading:
            title = heading.group("title").strip()
            del body[first]
        else:
            title = CALLOUT_DEFAULT_TITLES.get(callout_type, callout_type.capitalize())

    icon = CALLOUT_ICONS.get(callout_type)
    icon_html = (
        icon_svg(icon, "callout-icon")
        if icon and not CALLOUT_NO_ICON_ATTR_REGEX.search(attrs)
        else ""
    )

    return (
        f'<div class="callout callout-{callout_type}">'
        f'<div class="callout-header">{icon_html}'
        f'<span class="callout-title">{escape(title)}</span></div>'
        f'<div class="callout-body">{render_markdown("\n".join(body))}</div>'
        "</div>"
    )
