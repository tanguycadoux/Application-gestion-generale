"""Images des notes : références en base, chemins, URL externes."""

import re
from pathlib import PurePosixPath

from django.templatetags.static import static

from images.models import Image

IMAGE_MISSING_PATH = "note_taking/img/image-missing.svg"

# Image telle qu'écrite dans une note : ![légende](chemin/vers/image.png)
IMAGE_PATH_REGEX = re.compile(r"\!\[[^\]]*\]\((?P<path>[^)]+)\)")

# Image référencée en base après analyse : ![légende](image:<pk>){attributs}
IMAGE_REF_REGEX = re.compile(
    r"\!\[(?P<alt>[^\]]*)\]\(image:(?P<pk>\d+)\)(?P<attrs>\{[^}]*\})?"
)


# Image désignée par une URL complète ou absolue : pas une image importée.
EXTERNAL_URL_REGEX = re.compile(r"^([a-z][a-z0-9+.-]*://|/|data:)", re.IGNORECASE)

# Image sur un autre serveur, avec son titre et ses attributs éventuels :
# ![légende](https://…/a.png "titre"){width=50%}. Elle n'est pas chargée (#220).
REMOTE_IMAGE_REGEX = re.compile(
    r"\!\[(?P<alt>[^\]]*)\]\((?P<url>[a-z][a-z0-9+.-]*://[^)\s]+)"
    r"(?:\s+\"[^\"]*\")?\)(?:\{[^}]*\})?",
    re.IGNORECASE,
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


def resolve_image_paths(content: str) -> str:
    """Remplace les chemins d'images par l'URL de l'image importée de même nom.

    Une image inconnue est remplacée par l'image de remplacement ; une URL
    externe est conservée.
    """

    def repl(match: re.Match[str]) -> str:
        path = match.group("path")
        name = image_name(path)
        if name is None:
            return match.group(0)

        image = Image.objects.filter(name=name).first()
        url = image.file.url if image else static(IMAGE_MISSING_PATH)
        return match.group(0).replace(path, url)

    return IMAGE_PATH_REGEX.sub(repl, content)


def image_name(path: str) -> str | None:
    """Nom de l'image importée désignée par un chemin, ou None pour une URL externe.

    Seul le nom de fichier compte, quel que soit le dossier, écrit avec / ou \\.
    Règle commune à l'analyse, au rendu et à l'export (#220).
    """
    if EXTERNAL_URL_REGEX.match(path):
        return None
    return PurePosixPath(path.replace("\\", "/")).name


def remote_images_as_links(content: str) -> str:
    """Remplace chaque image sur un autre serveur par un lien vers son adresse.

    Les notes sont privées : le navigateur ne contacte aucun serveur tiers (#220).
    Le texte du lien est la légende, ou l'adresse sans légende.
    """

    def repl(match: re.Match[str]) -> str:
        url = match.group("url")
        return f"[{match.group('alt') or url}]({url})"

    return REMOTE_IMAGE_REGEX.sub(repl, content)
