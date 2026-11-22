"""Rendu d'une note et d'une note part : assemblage des étapes du rendu."""

from .blocks import render_markdown
from .floats import number_floats
from .headings import HEADING_TAG_REGEX, add_heading_ids, shift_heading
from .images import (
    remote_images_as_links,
    resolve_image_paths,
    resolve_image_refs,
)


def render_note_part(content: str) -> str:
    return number_floats(
        render_markdown(remote_images_as_links(resolve_image_refs(content)))
    )


def render_note_body(body: str, heading_ids: bool = False) -> str:
    """Rend le body complet d'une note, tel qu'écrit dans le fichier qmd.

    Les titres sont décalés d'un niveau (# devient h2) : la page qui l'affiche
    a son propre h1. Les blocs `{.metadata}` s'affichent en pastilles ; les
    tableaux et figures sont numérotés (`number_floats`). Avec `heading_ids`,
    chaque titre reçoit son identifiant (`add_heading_ids`), pour qu'un lien
    mène à sa section (#201).
    """
    html = number_floats(
        render_markdown(remote_images_as_links(resolve_image_paths(body)))
    )
    html = HEADING_TAG_REGEX.sub(shift_heading, html)
    return add_heading_ids(html) if heading_ids else html
