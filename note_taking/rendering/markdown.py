"""Rendu Markdown filtré, sans les blocs Quarto : extensions et filtrage."""

import markdown

from .figures import ImplicitFiguresExtension
from .inline import MathExtension, SuperscriptSubscriptExtension
from .lists import PandocListsExtension, TaskListExtension, task_checkboxes
from .sanitize import lazy_images, sanitize_html, scrollable_tables
from .tables import TableCaptionExtension


class NoSetextHeadingsExtension(markdown.Extension):
    """Désactive les titres « setext » (texte souligné de - ou de =).

    Les notes n'utilisent que les titres en #, sur lesquels repose le découpage en
    passages. Sans cela, un élément de liste vide (« - ») après un élément de
    liste ferait de celui-ci un titre, là où Quarto affiche une liste (#124).
    """

    def extendMarkdown(self, md: markdown.Markdown) -> None:
        md.parser.blockprocessors.deregister("setextheader")


MARKDOWN_EXTENSIONS: list[str | markdown.Extension] = [
    "fenced_code",
    "tables",
    "attr_list",
    # Un changement de type de liste (numéros, puces) commence une autre liste,
    # et une liste numérotée garde son premier numéro, comme dans Pandoc.
    "sane_lists",
    NoSetextHeadingsExtension(),
    PandocListsExtension(),
    TaskListExtension(),
    TableCaptionExtension(),
    SuperscriptSubscriptExtension(),
    MathExtension(),
    ImplicitFiguresExtension(),
]


def render_plain_markdown(text: str) -> str:
    """Markdown en HTML, filtré : tout ce qu'écrit l'utilisateur passe par ici.

    Le HTML des blocs Quarto (callouts, grilles, colonnes) est construit autour,
    à partir de valeurs échappées ou contrôlées, et n'a pas à être filtré.
    """
    html = sanitize_html(markdown.markdown(text, extensions=MARKDOWN_EXTENSIONS))
    return lazy_images(scrollable_tables(task_checkboxes(html)))
