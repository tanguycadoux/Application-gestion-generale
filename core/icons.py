"""Icônes Material Symbols (Rounded, 24 px) en SVG, rangées dans static/icons/ (#218).

Elles sont recopiées dans les pages (SVG inline) : pas de police chargée depuis
Internet, et pas de nom d'icône affiché le temps du chargement.
"""

import re
import urllib.error
import urllib.request
from functools import cache
from pathlib import Path

from django.conf import settings
from django.utils.html import format_html
from django.utils.safestring import SafeString, mark_safe

ICONS_DIR = Path(settings.BASE_DIR) / "static" / "icons"
SOURCE_URL = (
    "https://raw.githubusercontent.com/google/material-design-icons/master/symbols/web/"
    "{name}/materialsymbolsrounded/{name}_24px.svg"
)
NAME_REGEX = re.compile(r"^[a-z0-9_]+$")
SVG_REGEX = re.compile(
    r'<svg[^>]*viewBox="(?P<view_box>[^"]+)"[^>]*>(?P<inner>.*)</svg>', re.DOTALL
)

# Taille d'une icône sans classe : 24 px, celle de la police qu'elles remplacent.
DEFAULT_CLASSES = "size-6 shrink-0"


class UnknownIconError(LookupError):
    pass


@cache
def icon_parts(name: str) -> tuple[str, str]:
    """(viewBox, contenu) d'une icône de static/icons/."""
    path = ICONS_DIR / f"{name}.svg"
    if not NAME_REGEX.match(name) or not path.exists():
        raise UnknownIconError(
            f"Icône inconnue : {name!r}. L'ajouter avec "
            f"`python manage.py add_icon {name}`."
        )
    match = SVG_REGEX.search(path.read_text(encoding="utf-8"))
    if match is None:
        raise UnknownIconError(f"{path} n'est pas un SVG Material Symbols.")
    return match.group("view_box"), match.group("inner")


def icon_svg(name: str, classes: str = DEFAULT_CLASSES, label: str = "") -> SafeString:
    """Icône inline, de la couleur du texte (`currentColor`).

    Décorative par défaut (`aria-hidden`) ; avec `label`, une icône seule qui
    porte un sens : `role="img"` et le libellé en `aria-label`.
    """
    view_box, inner = icon_parts(name)
    a11y = (
        format_html('role="img" aria-label="{}"', label)
        if label
        else mark_safe('aria-hidden="true"')
    )
    return format_html(
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="{}" class="{}" '
        'fill="currentColor" {} focusable="false">{}</svg>',
        view_box,
        classes,
        a11y,
        mark_safe(inner),  # lu dans nos propres fichiers de static/icons/
    )


def download_icon(name: str) -> Path:
    """Télécharge une icône du dépôt officiel de Google dans static/icons/."""
    if not NAME_REGEX.match(name):
        raise UnknownIconError(
            f"Nom d'icône invalide : {name!r} (minuscules, chiffres et _)."
        )
    try:
        with urllib.request.urlopen(
            SOURCE_URL.format(name=name), timeout=10
        ) as response:
            text = response.read().decode("utf-8")
    except urllib.error.HTTPError as error:
        if error.code == 404:
            raise UnknownIconError(
                f"Icône inconnue de Material Symbols : {name!r}."
            ) from None
        raise
    if not SVG_REGEX.search(text):
        raise UnknownIconError(f"La réponse pour {name!r} n'est pas un SVG.")
    path = ICONS_DIR / f"{name}.svg"
    path.write_text(text, encoding="utf-8")
    icon_parts.cache_clear()
    return path
