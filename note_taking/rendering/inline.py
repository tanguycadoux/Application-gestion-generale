"""Motifs en ligne de Pandoc : exposants, indices, barré, souligné et formules LaTeX."""

import re
import xml.etree.ElementTree as etree

import markdown

# Exposant ^…^ et indice ~…~ : sans espace, sauf échappée (« \ »). Barré ~~…~~,
# qui ne commence ni ne finit par une espace.
SUPERSCRIPT_REGEX = r"\^(?P<text>(?:\\ |[^\s^])+)\^"
SUBSCRIPT_REGEX = r"~(?P<text>(?:\\ |[^\s~])+)~"
STRIKEOUT_REGEX = r"~~(?P<text>(?!\s).+?)(?<!\s)~~"


class SuperscriptSubscriptExtension(markdown.Extension):
    """Exposants, indices et barré, comme dans Quarto (#271).

    Extensions `superscript`, `subscript` et `strikeout` du Markdown de Pandoc.
    Le barré passe avant l'indice, qui utilise lui aussi le tilde. « \\^ » et
    « \\~ » restent du texte.
    """

    def extendMarkdown(self, md: markdown.Markdown) -> None:
        md.ESCAPED_CHARS.extend(["^", "~"])
        # Avant em_strong (60) : l'emphase reste rendue dans un exposant.
        for regex, tag, name, priority in (
            (STRIKEOUT_REGEX, "del", "strikeout", 70),
            (SUPERSCRIPT_REGEX, "sup", "superscript", 65),
            (SUBSCRIPT_REGEX, "sub", "subscript", 64),
        ):
            md.inlinePatterns.register(
                TagInlineProcessor(regex, tag, md), name, priority
            )


class TagInlineProcessor(markdown.inlinepatterns.InlineProcessor):
    """Entoure le texte du motif d'une balise ; « \\ » y est une espace insécable."""

    def __init__(self, pattern: str, tag: str, md: markdown.Markdown):
        super().__init__(pattern, md)
        self.tag = tag

    def handleMatch(  # type: ignore[override]
        self, m: re.Match[str], data: str
    ) -> tuple[etree.Element, int, int]:
        element = etree.Element(self.tag)
        element.text = m.group("text").replace("\\ ", " ")
        return element, m.start(0), m.end(0)


class UnderlineExtension(markdown.Extension):
    """Souligné `[texte]{.underline}`, comme dans Quarto (#434).

    De l'extension `bracketed_spans` de Pandoc, seule cette classe est reconnue :
    d'autres attributs laissent le tout en texte (`docs/ecarts-pandoc.md`).
    """

    def extendMarkdown(self, md: markdown.Markdown) -> None:
        # Après le code, les liens et les images (140), qui gardent leurs crochets et où
        # le souligné est rendu ensuite ; avant un lien par référence `[texte]` (130).
        md.inlinePatterns.register(
            UnderlineInlineProcessor(r"(?<!!)\[", md), "underline", 135
        )


class UnderlineInlineProcessor(markdown.inlinepatterns.LinkInlineProcessor):
    """Un lien dont les attributs remplacent l'adresse : mêmes crochets appariés."""

    CLASS_REGEX = re.compile(r"\{[ ]*\.underline[ ]*\}")

    def handleMatch(  # type: ignore[override]
        self, m: re.Match[str], data: str
    ) -> tuple[etree.Element | None, int | None, int | None]:
        text, index, closed = self.getText(data, m.end(0))
        found = self.CLASS_REGEX.match(data, index) if closed else None
        if found is None:
            return None, None, None
        element = etree.Element("span", {"class": "underline"})
        element.text = text
        return element, m.start(0), found.end()


# Formule en bloc $$…$$, éventuellement sur plusieurs lignes.
DISPLAY_MATH_REGEX = r"(?<!\\)\$\$(?P<tex>.+?)\$\$"
# Formule en ligne $…$ : pas d'espace après le premier $ ni avant le second, et
# pas de chiffre juste après (« de 5$ à 6$ » n'est pas une formule).
INLINE_MATH_REGEX = r"(?<!\\)\$(?![\s$])(?P<tex>(?:[^$\\]|\\.)+?)(?<!\s)\$(?!\d)"


class MathExtension(markdown.Extension):
    """Formules LaTeX $…$ et $$…$$, comme dans Quarto (#99).

    La formule est gardée telle qu'écrite, sous la forme de Pandoc avec MathJax :
    `<span class="math inline">\\(…\\)</span>`, ou `math display` et `\\[…\\]`.
    Le script `math.js` l'affiche ensuite avec KaTeX. Les motifs passent avant
    tous les autres, sauf le code : ni l'emphase, ni les exposants, ni les
    caractères échappés ne touchent une formule.
    """

    def extendMarkdown(self, md: markdown.Markdown) -> None:
        md.ESCAPED_CHARS.append("$")
        # Après backtick (190), avant escape (180).
        md.inlinePatterns.register(
            MathInlineProcessor(DISPLAY_MATH_REGEX, "display", md), "display_math", 186
        )
        md.inlinePatterns.register(
            MathInlineProcessor(INLINE_MATH_REGEX, "inline", md), "inline_math", 185
        )


class MathInlineProcessor(markdown.inlinepatterns.InlineProcessor):
    DELIMITERS = {"inline": ("\\(", "\\)"), "display": ("\\[", "\\]")}

    def __init__(self, pattern: str, mode: str, md: markdown.Markdown):
        super().__init__(pattern, md)
        self.mode = mode

    def handleMatch(  # type: ignore[override]
        self, m: re.Match[str], data: str
    ) -> tuple[etree.Element, int, int]:
        start, end = self.DELIMITERS[self.mode]
        element = etree.Element("span", {"class": f"math {self.mode}"})
        element.text = markdown.util.AtomicString(f"{start}{m.group('tex')}{end}")
        return element, m.start(0), m.end(0)
