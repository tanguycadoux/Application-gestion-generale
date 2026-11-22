"""Légendes de tableau de Pandoc dans Python-Markdown."""

import re
import xml.etree.ElementTree as etree

import markdown

# Légende de tableau : paragraphe qui commence par « : » ou « Table: ».
TABLE_CAPTION_REGEX = re.compile(r"^(?:[Tt]able)?:")
# Ligne d'un tableau, qui commence par une barre verticale.
TABLE_ROW_REGEX = re.compile(r"^ {0,3}\|")
# Attributs Pandoc en fin de légende : {#tbl-x .classe}.
CAPTION_ATTRS_REGEX = re.compile(r"\s*\{(?P<attrs>[^}]*)\}\s*$")


class TableCaptionExtension(markdown.Extension):
    """Légendes de tableau « : Légende », comme dans Quarto (#230).

    Comme Pandoc, un paragraphe qui commence par « : » ou « Table: », juste
    avant ou juste après un tableau, devient sa légende (`<caption>`) ; celle
    d'avant l'emporte. Des attributs `{#tbl-x .classe}` en fin de légende vont
    au tableau.
    """

    def extendMarkdown(self, md: markdown.Markdown) -> None:
        md.preprocessors.register(TableCaptionPreprocessor(md), "table_caption", 23)
        # Après inline (20) : la légende garde sa mise en forme. Avant unescape
        # (0) : « \: » échappé ne commence pas une légende.
        md.treeprocessors.register(TableCaptionTreeprocessor(md), "table_caption", 5)


class TableCaptionPreprocessor(markdown.preprocessors.Preprocessor):
    """Sépare d'une ligne vide une légende collée à son tableau.

    Pandoc accepte une légende sans ligne vide ; Python-Markdown n'y verrait
    qu'un seul paragraphe.
    """

    def run(self, lines: list[str]) -> list[str]:
        result: list[str] = []
        for index, line in enumerate(lines):
            caption = TABLE_CAPTION_REGEX.match(line)
            if caption and result and TABLE_ROW_REGEX.match(result[-1]):
                result.append("")
            result.append(line)
            following = lines[index + 1] if index + 1 < len(lines) else ""
            if caption and TABLE_ROW_REGEX.match(following):
                result.append("")
        return result


class TableCaptionTreeprocessor(markdown.treeprocessors.Treeprocessor):
    def run(self, root: etree.Element) -> None:
        parents = [
            element
            for element in root.iter()
            if any(child.tag == "table" for child in element)
        ]
        for parent in parents:
            for table in [child for child in parent if child.tag == "table"]:
                children = list(parent)
                index = children.index(table)
                # Les voisins dans l'ordre de Pandoc : avant, puis après.
                before = children[index - 1] if index else None
                after = children[index + 1] if index + 1 < len(children) else None
                caption = next(
                    (
                        n
                        for n in (before, after)
                        if n is not None and is_table_caption(n)
                    ),
                    None,
                )
                if caption is not None:
                    parent.remove(caption)
                    add_table_caption(table, caption)


def is_table_caption(element: etree.Element) -> bool:
    return element.tag == "p" and bool(TABLE_CAPTION_REGEX.match(element.text or ""))


def add_table_caption(table: etree.Element, paragraph: etree.Element) -> None:
    """Fait du paragraphe la légende du tableau, ses attributs ceux du tableau."""
    caption = etree.Element("caption")
    table.insert(0, caption)
    caption.text = TABLE_CAPTION_REGEX.sub("", paragraph.text or "", count=1).lstrip()
    caption.extend(list(paragraph))

    last = caption[-1] if len(caption) else None
    text = (last.tail if last is not None else caption.text) or ""
    attrs = CAPTION_ATTRS_REGEX.search(text)
    if attrs:
        text = text[: attrs.start()]
        if last is not None:
            last.tail = text
        else:
            caption.text = text
        classes = []
        for token in attrs.group("attrs").split():
            if token.startswith("#"):
                table.set("id", token[1:])
            elif token.startswith("."):
                classes.append(token[1:])
        if classes:
            table.set("class", " ".join(classes))
