"""Images des notes : références en base, chemins, URL externes."""

import re
from pathlib import PurePosixPath

from django.templatetags.static import static

from images.models import Image

IMAGE_MISSING_PATH = "note_taking/img/image-missing.svg"

# Légende d'une image : des crochets appariés y sont permis, sur un niveau (un lien, du
# code, une formule, #453).
CAPTION = r"(?:\[[^\[\]]*\]|[^\]])*"

# Image telle qu'écrite dans une note : ![légende](chemin/vers/image.png)
IMAGE_PATH_REGEX = re.compile(rf"\!\[(?P<alt>{CAPTION})\]\((?P<path>[^)]+)\)")

# Image référencée en base après analyse : ![légende](image:<pk>){attributs}
IMAGE_REF_REGEX = re.compile(
    rf"\!\[(?P<alt>{CAPTION})\]\(image:(?P<pk>\d+)\)(?P<attrs>\{{[^}}]*\}})?"
)


# Image désignée par une URL complète ou absolue : pas une image importée.
EXTERNAL_URL_REGEX = re.compile(r"^([a-z][a-z0-9+.-]*://|/|data:)", re.IGNORECASE)

# Image entière, avec ses attributs éventuels. On cherche d'abord l'image, puis on regarde
# son chemin : un motif limité aux adresses distantes prendrait celle d'un lien de la
# légende pour celle de l'image (#453).
IMAGE_REGEX = re.compile(rf"{IMAGE_PATH_REGEX.pattern}(?:\{{[^}}]*\}})?")
# Chemin sur un autre serveur, avec son titre éventuel : https://…/a.png "titre".
# L'image n'est pas chargée (#220).
REMOTE_PATH_REGEX = re.compile(
    r"(?P<url>[a-z][a-z0-9+.-]*://\S+)(?:\s+\"[^\"]*\")?", re.IGNORECASE
)
# Lien dans une légende, dont on ne garde que le texte.
CAPTION_LINK_REGEX = re.compile(r"\[(?P<text>[^\[\]]*)\]\([^)]*\)")


def with_path(match: re.Match[str], path: str) -> str:
    """L'image trouvée par `IMAGE_PATH_REGEX` avec ce chemin ; la légende ne change
    pas, même si elle reprend l'ancien (`![banc.png](banc.png)`)."""
    start, end = (position - match.start() for position in match.span("path"))
    return match[0][:start] + path + match[0][end:]


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
        return with_path(match, url)

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
    Le texte du lien est la légende, ou l'adresse sans légende ; un lien de la légende
    n'y garde que son texte, un lien n'en contenant pas d'autre.
    """

    def repl(match: re.Match[str]) -> str:
        remote = REMOTE_PATH_REGEX.fullmatch(match["path"])
        if remote is None:
            return match[0]
        text = CAPTION_LINK_REGEX.sub(lambda link: link["text"], match["alt"])
        return f"[{text or remote['url']}]({remote['url']})"

    return IMAGE_REGEX.sub(repl, content)
