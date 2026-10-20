"""Rendu HTML des notes : Markdown et références d'images."""

import re
from pathlib import Path

import markdown
from django.templatetags.static import static
from django.utils.html import escape

from images.models import Image

from .qmd.parser import BLOCK_END, METADATA_BLOCK_START

MARKDOWN_EXTENSIONS = ["fenced_code", "tables", "attr_list"]

IMAGE_MISSING_PATH = "note_taking/img/image-missing.svg"

# Image telle qu'écrite dans une note : ![légende](chemin/vers/image.png)
IMAGE_PATH_REGEX = re.compile(r"\!\[[^\]]*\]\((?P<path>[^)]+)\)")

# Image référencée en base après analyse : ![légende](image:<pk>){attributs}
IMAGE_REF_REGEX = re.compile(
    r"\!\[(?P<alt>[^\]]*)\]\(image:(?P<pk>\d+)\)(?P<attrs>\{[^}]*\})?"
)

# Image désignée par une URL complète ou absolue, laissée telle quelle.
EXTERNAL_URL_REGEX = re.compile(r"^([a-z][a-z0-9+.-]*://|/|data:)", re.IGNORECASE)


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
    callout, sinon le titre par défaut du type.
    """
    callout_type = start.group("type")
    title_attr = CALLOUT_TITLE_ATTR_REGEX.search(start.group("attrs"))
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

    return (
        f'<div class="callout callout-{callout_type}">'
        f'<div class="callout-header">{escape(title)}</div>'
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
    """Rend le body complet d'une note, tel qu'écrit dans le fichier qmd."""
    return render_markdown(resolve_image_paths(strip_metadata_blocks(body)))


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
