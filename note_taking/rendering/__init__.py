"""Rendu HTML des notes : Markdown et références d'images.

Les sous-modules, du plus simple au plus composé (aucun n'importe un suivant) :

- `sanitize` : filtrage du HTML (nh3) et retouches du HTML filtré ;
- `lists`, `tables`, `inline`, `figures` : extensions Python-Markdown fidèles à
  Pandoc ;
- `markdown` : Markdown filtré, sans les blocs Quarto (`render_plain_markdown`) ;
- `images` : références, chemins et URL externes des images ;
- `divs`, `blocks` : blocs Quarto `:::` (callouts, colonnes, métadonnées),
  rendus par `render_markdown` ;
- `floats` : numéros des tableaux et figures, références croisées ;
- `new_tab` : liens ouverts dans un nouvel onglet (#438) ;
- `headings` : décalage et identifiants des titres ;
- `note_links` : liens vers d'autres notes, `AAAA-MM-JJ.qmd` (#206) ;
- `empty_links` : texte des liens qui n'en ont pas (#467) ;
- `notes` : assemblage, pour une note (`render_note_body`) et un passage
  (`render_passage`).

Les noms utilisés hors du paquet sont réexportés ici.
"""

from .blocks import CALLOUT_DEFAULT_TITLES, CALLOUT_ICONS, render_markdown
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
    with_path,
)
from .markdown import render_plain_markdown
from .new_tab import without_new_tab_marks
from .notes import note_heading_ids, render_note_body, render_passage
from .sanitize import sanitize_html

__all__ = [
    "CALLOUT_DEFAULT_TITLES",
    "CALLOUT_ICONS",
    "IMAGE_MISSING_PATH",
    "IMAGE_PATH_REGEX",
    "IMAGE_REF_REGEX",
    "add_heading_ids",
    "heading_anchor",
    "heading_slug",
    "image_name",
    "note_heading_ids",
    "number_floats",
    "remote_images_as_links",
    "render_markdown",
    "render_note_body",
    "render_passage",
    "render_plain_markdown",
    "resolve_image_paths",
    "resolve_image_refs",
    "sanitize_html",
    "with_path",
    "without_new_tab_marks",
]
