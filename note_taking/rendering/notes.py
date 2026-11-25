"""Rendu d'une note et d'un passage : assemblage des étapes du rendu, et
identifiants des titres d'une note."""

from .blocks import render_markdown
from .empty_links import fill_empty_links
from .floats import number_floats
from .headings import (
    HEADING_TAG_REGEX,
    add_heading_ids,
    heading_anchor,
    heading_texts,
    shift_heading,
)
from .images import (
    remote_images_as_links,
    resolve_image_paths,
    resolve_image_refs,
)
from .new_tab import open_links_in_new_tab
from .note_links import resolve_note_links


def finish_links(html: str, heading_prefix: str = "") -> str:
    """Les liens du HTML rendu, une fois les titres identifiés : ce qui s'ajoute à un
    lien (texte, marque) n'entre pas dans l'identifiant d'un titre."""
    html = fill_empty_links(html, heading_prefix)
    return open_links_in_new_tab(resolve_note_links(html))


def render_passage(content: str, heading_prefix: str = "") -> str:
    """Rend le texte d'un passage, ou des passages assemblés en un document (#356).

    `heading_prefix` : donne aux titres un identifiant qui commence ainsi (#431), sans
    quoi celui d'un titre pourrait être celui d'un autre élément de la page.
    """
    html = number_floats(
        render_markdown(remote_images_as_links(resolve_image_refs(content)))
    )
    if heading_prefix:
        html = add_heading_ids(html, heading_prefix)
    return finish_links(html, heading_prefix)


def render_note_body(body: str, heading_ids: bool = False) -> str:
    """Rend le body complet d'une note, tel qu'écrit dans le fichier qmd.

    Les titres sont décalés d'un niveau (# devient h2) : la page qui l'affiche
    a son propre h1. Les blocs `{.metadata}` s'affichent en pastilles ; les
    tableaux et figures sont numérotés (`number_floats`), les liens vers
    d'autres notes mènent à leur page (`resolve_note_links`, #206), un lien sans texte
    affiche son adresse (`fill_empty_links`, #467). Avec
    `heading_ids`, chaque titre reçoit son identifiant (`add_heading_ids`), pour
    qu'un lien mène à sa section (#201). Les liens qui quittent la page s'ouvrent dans
    un nouvel onglet (`open_links_in_new_tab`, #438), en dernier : leur marque n'entre
    pas dans l'identifiant d'un titre.
    """
    html = number_floats(
        render_markdown(remote_images_as_links(resolve_image_paths(body)))
    )
    html = HEADING_TAG_REGEX.sub(shift_heading, html)
    return finish_links(add_heading_ids(html) if heading_ids else html)


def note_heading_ids(body: str, titles: list[str]) -> list[str]:
    """L'identifiant de chacun de ces titres dans la page de la note (#387).

    `titles` : les titres que l'analyse reconnaît, dans l'ordre. Ce sont les titres
    du premier niveau de la page, ceux de son plan (`note_outline`) ; les autres
    (dans une citation, un encadré) prennent aussi un identifiant, ce qui numérote
    les suivants : chaque titre est donc retrouvé, par son texte rendu, parmi ceux du
    plan, à la suite du précédent. Un titre introuvable (écrit dans un bloc
    `:::` de colonnes, par exemple) prend l'identifiant de son texte seul.
    """
    # Import local : le plan se calcule sur le HTML rendu par ce module.
    from ..note_outline import outline_sections

    entries = outline_sections(render_note_body(body, heading_ids=True)).entries
    ids, cursor = [], 0
    for title in titles:
        wanted = heading_texts(render_note_body("# " + title))
        text = wanted[0][0] if wanted else ""
        found = next(
            (
                index
                for index in range(cursor, len(entries))
                if entries[index].text == text
            ),
            None,
        )
        if found is None:
            ids.append(heading_anchor(title) or "")
            continue
        ids.append(entries[found].id)
        cursor = found + 1
    return ids
