"""Rendu HTML des notes : Markdown et références d'images."""

import re

import markdown
from django.templatetags.static import static
from django.utils.html import escape

from images.models import Image

MARKDOWN_EXTENSIONS = ["fenced_code", "tables", "attr_list"]

IMAGE_MISSING_PATH = "note_taking/img/image-missing.svg"

# Image telle qu'écrite dans une note : ![légende](chemin/vers/image.png)
IMAGE_PATH_REGEX = re.compile(r"\!\[[^\]]*\]\((?P<path>[^)]+)\)")

# Image référencée en base après analyse : ![légende](image:<pk>){attributs}
IMAGE_REF_REGEX = re.compile(
    r"\!\[(?P<alt>[^\]]*)\]\(image:(?P<pk>\d+)\)(?P<attrs>\{[^}]*\})?"
)


# Callout Quarto : ::: {.callout-<type> title="…"} … :::
CALLOUT_START_REGEX = re.compile(r"^:::\s*\{\.callout-(?P<type>\w+)(?P<attrs>[^}]*)\}$")
CALLOUT_END = ":::"
CALLOUT_TITLE_ATTR_REGEX = re.compile(r'title="(?P<title>[^"]*)"')
CALLOUT_HEADING_REGEX = re.compile(r"^#+\s+(?P<title>.+)$")

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
    """Rend du Markdown en HTML, callouts Quarto compris."""
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

        start = None if in_code_block else CALLOUT_START_REGEX.match(stripped)
        end = find_callout_end(lines, index) if start else None
        if start and end is not None:
            html.append(render_plain_markdown("\n".join(pending)))
            pending = []
            html.append(render_callout(start, lines[index + 1 : end]))
            index = end + 1
            continue

        pending.append(line)
        index += 1

    html.append(render_plain_markdown("\n".join(pending)))
    return "\n".join(part for part in html if part)


def render_plain_markdown(text: str) -> str:
    return markdown.markdown(text, extensions=MARKDOWN_EXTENSIONS)


def find_callout_end(lines: list[str], start: int) -> int | None:
    """Indice de la ligne fermant le callout ouvert à `start`, s'il existe."""
    for index in range(start + 1, len(lines)):
        if lines[index].strip() == CALLOUT_END:
            return index
    return None


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
