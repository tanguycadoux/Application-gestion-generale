"""Rendu HTML des notes : Markdown et références d'images."""

import re
from pathlib import Path

import markdown
from django.templatetags.static import static
from django.utils.html import escape

from images.models import Image

from .qmd.parser import BLOCK_END, METADATA_BLOCK_START


class NoSetextHeadingsExtension(markdown.Extension):
    """Désactive les titres « setext » (texte souligné de - ou de =).

    Les notes n'utilisent que les titres en #, sur lesquels repose le découpage en
    note parts. Sans cela, un élément de liste vide (« - ») après un élément de
    liste ferait de celui-ci un titre, là où Quarto affiche une liste (#124).
    """

    def extendMarkdown(self, md: markdown.Markdown) -> None:
        md.parser.blockprocessors.deregister("setextheader")


MARKDOWN_EXTENSIONS: list[str | markdown.Extension] = [
    "fenced_code",
    "tables",
    "attr_list",
    NoSetextHeadingsExtension(),
]

IMAGE_MISSING_PATH = "note_taking/img/image-missing.svg"

# Image telle qu'écrite dans une note : ![légende](chemin/vers/image.png)
IMAGE_PATH_REGEX = re.compile(r"\!\[[^\]]*\]\((?P<path>[^)]+)\)")

# Image référencée en base après analyse : ![légende](image:<pk>){attributs}
IMAGE_REF_REGEX = re.compile(
    r"\!\[(?P<alt>[^\]]*)\]\(image:(?P<pk>\d+)\)(?P<attrs>\{[^}]*\})?"
)

# Balise de titre ouvrante ou fermante du HTML rendu : <h2 …> ou </h2>.
HEADING_TAG_REGEX = re.compile(r"<(?P<slash>/?)h(?P<level>[1-6])\b")

# Image désignée par une URL complète ou absolue, laissée telle quelle.
EXTERNAL_URL_REGEX = re.compile(r"^([a-z][a-z0-9+.-]*://|/|data:)", re.IGNORECASE)


# Callout Quarto : ::: {.callout-<type> title="…"} … :::
CALLOUT_START_REGEX = re.compile(r"^:::\s*\{\.callout-(?P<type>\w+)(?P<attrs>[^}]*)\}$")
CALLOUT_TITLE_ATTR_REGEX = re.compile(r'title="(?P<title>[^"]*)"')
CALLOUT_HEADING_REGEX = re.compile(r"^#+\s+(?P<title>.+)$")

# Blocs Quarto ::: {…} … :::, éventuellement imbriqués
DIV_START_REGEX = re.compile(r"^:::+\s*\{[^}]*\}$")
DIV_END_REGEX = re.compile(r"^:::+$")
DIV_ID_REGEX = re.compile(r"#(?P<id>[\w-]+)")

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

CODE_FENCE = "```"


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


def render_plain_markdown(text: str) -> str:
    return markdown.markdown(text, extensions=MARKDOWN_EXTENSIONS)


def match_block_start(line: str):
    """Début de bloc rendu à part (callout, figure, colonnes) et son rendu."""
    for regex, render_block in (
        (CALLOUT_START_REGEX, render_callout),
        (LAYOUT_START_REGEX, render_layout),
        (COLUMNS_START_REGEX, render_columns),
    ):
        start = regex.match(line)
        if start:
            return start, render_block
    return None


def find_block_end(lines: list[str], start: int) -> int | None:
    """Indice de la ligne fermant le bloc ouvert à `start`, s'il existe.

    Tient compte des blocs imbriqués ; les blocs de code sont ignorés.
    """
    depth = 1
    in_code_block = False
    for index in range(start + 1, len(lines)):
        stripped = lines[index].strip()
        if stripped.startswith(CODE_FENCE):
            in_code_block = not in_code_block
        elif in_code_block:
            continue
        elif DIV_START_REGEX.match(stripped):
            depth += 1
        elif DIV_END_REGEX.match(stripped):
            depth -= 1
            if depth == 0:
                return index
    return None


def split_blocks(lines: list[str]) -> list[str]:
    """Découpe en blocs séparés par des lignes vides, hors code et blocs `:::`."""
    blocks: list[list[str]] = [[]]
    depth = 0
    in_code_block = False
    for line in lines:
        stripped = line.strip()
        if stripped.startswith(CODE_FENCE):
            in_code_block = not in_code_block
        elif not in_code_block and DIV_START_REGEX.match(stripped):
            depth += 1
        elif not in_code_block and depth and DIV_END_REGEX.match(stripped):
            depth -= 1

        if not stripped and not in_code_block and depth == 0:
            blocks.append([])
        else:
            blocks[-1].append(line)
    return ["\n".join(block) for block in blocks if block]


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
        '<figcaption class="mt-2 text-sm text-center text-gray-600">'
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
        f'<span class="material-symbols-rounded callout-icon" aria-hidden="true">'
        f"{icon}</span>"
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


def resolve_image_refs(content: str) -> str:
    """Remplace les références `image:<pk>` par l'URL du fichier de l'image."""

    def repl(match: re.Match[str]) -> str:
        alt = match.group("alt")
        attrs = match.group("attrs") or ""

        try:
            url = Image.objects.get(pk=match.group("pk")).file.url
        except Image.DoesNotExist:
            url = static(IMAGE_MISSING_PATH)

        return f"![{alt}]({url}){attrs}"

    return IMAGE_REF_REGEX.sub(repl, content)


def render_note_part(content: str) -> str:
    return render_markdown(resolve_image_refs(content))


def render_note_body(body: str) -> str:
    """Rend le body complet d'une note, tel qu'écrit dans le fichier qmd.

    Les titres sont décalés d'un niveau (# devient h2) : la page qui l'affiche
    a son propre h1.
    """
    html = render_markdown(resolve_image_paths(strip_metadata_blocks(body)))
    return HEADING_TAG_REGEX.sub(shift_heading, html)


def shift_heading(match: re.Match[str]) -> str:
    level = min(int(match.group("level")) + 1, 6)
    return f"<{match.group('slash')}h{level}"


def strip_metadata_blocks(text: str) -> str:
    """Retire les blocs `::: {.metadata}`, lus à l'analyse mais pas affichés."""
    kept: list[str] = []
    in_code_block = False
    in_metadata_block = False

    for line in text.split("\n"):
        stripped = line.strip()
        if stripped.startswith(CODE_FENCE) and not in_metadata_block:
            in_code_block = not in_code_block

        if in_metadata_block:
            in_metadata_block = stripped != BLOCK_END
        elif not in_code_block and stripped == METADATA_BLOCK_START:
            in_metadata_block = True
        else:
            kept.append(line)

    return "\n".join(kept)


def resolve_image_paths(content: str) -> str:
    """Remplace les chemins d'images par l'URL de l'image importée de même nom.

    Une image inconnue est remplacée par l'image de remplacement ; une URL
    externe est conservée.
    """

    def repl(match: re.Match[str]) -> str:
        path = match.group("path")
        if EXTERNAL_URL_REGEX.match(path):
            return match.group(0)

        image = Image.objects.filter(name=Path(path).name).first()
        url = image.file.url if image else static(IMAGE_MISSING_PATH)
        return match.group(0).replace(path, url)

    return IMAGE_PATH_REGEX.sub(repl, content)
