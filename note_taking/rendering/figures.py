"""Figures implicites de Pandoc : une image seule dans son paragraphe (#422)."""

import html as html_module
import re
import xml.etree.ElementTree as etree

import markdown
from markdown.inlinepatterns import (
    IMAGE_LINK_RE,
    IMAGE_REFERENCE_RE,
    ImageInlineProcessor,
    ImageReferenceInlineProcessor,
    InlineProcessor,
    ShortImageReferenceInlineProcessor,
)
from markdown.util import HTML_PLACEHOLDER_RE

from .sanitize import is_remote

FIGURE_CLASSES = "my-2"
FIGCAPTION_CLASSES = "mt-2 text-sm text-center text-slate-600"
HTML_TAG_REGEX = re.compile(r"<[^>]*>")


class ImplicitFiguresExtension(markdown.Extension):
    """Extension `implicit_figures` de Pandoc, celle de Quarto.

    Une image seule dans son paragraphe, avec un texte, devient une `<figure>` dont ce
    texte est la légende, Markdown compris (gras, formule, lien). Un identifiant
    `{#fig-…}` passe à la figure, avec ou sans légende : `floats.number_floats` la
    numérote. Toute autre image reste dans sa ligne, sans légende.
    """

    def extendMarkdown(self, md: markdown.Markdown) -> None:
        for processor, regex, name, priority in (
            (CaptionedImage, IMAGE_LINK_RE, "image_link", 150),
            (CaptionedImageReference, IMAGE_REFERENCE_RE, "image_reference", 140),
            (
                CaptionedShortImageReference,
                IMAGE_REFERENCE_RE,
                "short_image_ref",
                125,
            ),
        ):
            md.inlinePatterns.register(processor(regex, md), name, priority)
        # Après attr_list (8), qui pose les attributs ; avant unescape (0).
        md.treeprocessors.register(FigureTreeprocessor(md), "implicit_figures", 5)


class CaptionMixin(InlineProcessor):
    """Garde le texte entre crochets dans l'image, pour que le Markdown en soit rendu ;
    `FigureTreeprocessor` l'en retire toujours."""

    def handleMatch(  # type: ignore[override]
        self, m: re.Match[str], data: str
    ) -> tuple[etree.Element | str | None, int | None, int | None]:
        element, start, end = super().handleMatch(m, data)
        if isinstance(element, etree.Element):
            element.text = self.getText(data, m.end(0))[0]  # type: ignore[attr-defined]
        return element, start, end


class CaptionedImage(CaptionMixin, ImageInlineProcessor):
    pass


class CaptionedImageReference(CaptionMixin, ImageReferenceInlineProcessor):
    pass


class CaptionedShortImageReference(CaptionMixin, ShortImageReferenceInlineProcessor):
    pass


class FigureTreeprocessor(markdown.treeprocessors.Treeprocessor):
    def run(self, root: etree.Element) -> None:
        for paragraph in list(root.iter("p")):
            if is_alone(paragraph):
                self.to_figure(paragraph)
        for image in root.iter("img"):
            self.set_alt(image)
            image.text = None
            for child in list(image):
                image.remove(child)

    def to_figure(self, paragraph: etree.Element) -> None:
        image = paragraph[0]
        figure_id = image.get("id", "")
        has_caption = bool("".join(image.itertext()).strip())
        if not has_caption and not figure_id.startswith("fig-"):
            return
        paragraph.tag = "figure"
        paragraph.text = image.tail = None
        paragraph.set("class", FIGURE_CLASSES)
        if figure_id.startswith("fig-"):
            paragraph.set("id", image.attrib.pop("id"))
        if has_caption:
            caption = etree.SubElement(
                paragraph, "figcaption", {"class": FIGCAPTION_CLASSES}
            )
            caption.text = image.text
            caption.extend(list(image))

    def set_alt(self, image: etree.Element) -> None:
        """L'`alt` : `fig-alt` s'il est donné, sinon le texte sans sa mise en forme."""
        alt = image.attrib.pop("fig-alt", None)
        if alt is None:
            alt = HTML_PLACEHOLDER_RE.sub(self.raw_text, "".join(image.itertext()))
        image.set("alt", alt)

    def raw_text(self, match: re.Match[str]) -> str:
        """Le texte d'un morceau de HTML (balise, entité) que Markdown a mis de côté."""
        raw = self.md.htmlStash.rawHtmlBlocks[int(match.group(1))]
        return html_module.unescape(HTML_TAG_REGEX.sub("", str(raw)))


def is_alone(paragraph: etree.Element) -> bool:
    """Le paragraphe ne contient qu'une image, qui n'est pas sur un autre serveur : elle
    deviendrait un lien (#458)."""
    return (
        len(paragraph) == 1
        and paragraph[0].tag == "img"
        and not is_remote(paragraph[0].get("src", ""))
        and not (paragraph.text or "").strip()
        and not (paragraph[0].tail or "").strip()
    )
