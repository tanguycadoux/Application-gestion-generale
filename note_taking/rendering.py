"""Rendu HTML des notes : Markdown et références d'images."""

import re

import markdown
from django.templatetags.static import static

from .models import NotePartImage

MARKDOWN_EXTENSIONS = ["fenced_code", "tables"]

IMAGE_MISSING_PATH = "img/image-missing.png"

# Image telle qu'écrite dans une note : ![légende](chemin/vers/image.png)
IMAGE_PATH_REGEX = re.compile(r"\!\[[^\]]*\]\((?P<path>[^)]+)\)")

# Image référencée en base après analyse : ![légende](image:<pk>){attributs}
IMAGE_REF_REGEX = re.compile(
    r"\!\[(?P<alt>[^\]]*)\]\(image:(?P<pk>\d+)\)(?P<attrs>\{[^}]*\})?"
)


def render_markdown(text: str) -> str:
    return markdown.markdown(text, extensions=MARKDOWN_EXTENSIONS)


def resolve_image_refs(content: str) -> str:
    """Remplace les références `image:<pk>` par l'URL du fichier de l'image."""

    def repl(match: re.Match[str]) -> str:
        alt = match.group("alt")
        attrs = match.group("attrs") or ""

        try:
            url = NotePartImage.objects.get(pk=match.group("pk")).file.url
        except NotePartImage.DoesNotExist:
            url = static(IMAGE_MISSING_PATH)

        return f"![{alt}]({url}){attrs}"

    return IMAGE_REF_REGEX.sub(repl, content)


def render_note_part(content: str) -> str:
    return render_markdown(resolve_image_refs(content))
