"""Rendu HTML des notes : Markdown et références d'images.

Les sous-modules, du plus simple au plus composé (aucun n'importe un suivant) :

- `sanitize` : filtrage du HTML (nh3) et retouches du HTML filtré ;
- `lists`, `tables`, `inline` : extensions Python-Markdown fidèles à Pandoc ;
- `markdown` : Markdown filtré, sans les blocs Quarto (`render_plain_markdown`) ;
- `images` : références, chemins et URL externes des images ;
- `divs`, `blocks` : blocs Quarto `:::` (callouts, colonnes, métadonnées),
  rendus par `render_markdown` ;
- `floats` : numéros des tableaux et figures, références croisées ;
- `headings` : décalage et identifiants des titres ;
- `notes` : assemblage, pour une note (`render_note_body`) et une note part
  (`render_note_part`).

Les noms utilisés hors du paquet sont réexportés ici.
"""

from .blocks import CALLOUT_ICONS, render_markdown
from .floats import number_floats
from .headings import add_heading_ids, heading_anchor, heading_slug
from .images import (
    IMAGE_MISSING_PATH,
    IMAGE_PATH_REGEX,
    IMAGE_REF_REGEX,
    image_name,
    remote_images_as_links,
    resolve_image_paths,
    resolve_image_refs,
)
from .markdown import render_plain_markdown
from .notes import render_note_body, render_note_part
from .sanitize import sanitize_html

__all__ = [
    "CALLOUT_ICONS",
    "IMAGE_MISSING_PATH",
    "IMAGE_PATH_REGEX",
    "IMAGE_REF_REGEX",
    "add_heading_ids",
    "heading_anchor",
    "heading_slug",
    "image_name",
    "number_floats",
    "remote_images_as_links",
    "render_markdown",
    "render_note_body",
    "render_note_part",
    "render_plain_markdown",
    "resolve_image_paths",
    "resolve_image_refs",
    "sanitize_html",
]
