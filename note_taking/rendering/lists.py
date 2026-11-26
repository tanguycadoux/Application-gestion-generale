"""Listes de Pandoc dans Python-Markdown : imbrication, marqueurs, cases."""

import re
import xml.etree.ElementTree as etree

import markdown
from markdown.blockprocessors import HRProcessor, ListIndentProcessor

from ..qmd.lists import LIST_ITEM_REGEX, Marker, parse_marker, text_column

ATX_HEADING_REGEX = re.compile(r"^#{1,6}(\s|$)")
# Pas d'indentation de Python-Markdown : un niveau de liste, un bloc de code.
MARKDOWN_INDENT = 4
# Élément d'un bloc de Python-Markdown, réindenté par `PandocListsPreprocessor`.
BLOCK_ITEM_REGEX = re.compile(r"^(?P<indent>(?: {4})*)(?:\d+\.|[*+-]) ")
# Lignes qui terminent une liste pour Python-Markdown : titre, trait horizontal.
BLOCK_END_REGEX = re.compile(rf"^#|{HRProcessor.RE}")
# Clôture d'un bloc de code délimité, lue après l'indentation de la ligne.
FENCE_REGEX = re.compile(r"(?P<fence>`{3,}|~{3,})")
# Ligne d'une citation, et son préfixe : `>` et une espace éventuelle.
QUOTE_REGEX = re.compile(r"^ {0,3}> ?")


class PandocListsExtension(markdown.Extension):
    """Imbrique les listes selon la règle de Pandoc, celle de Quarto (#229).

    Pour Pandoc, un élément est imbriqué si son marqueur commence au moins à la
    colonne du texte de l'élément parent : 2 espaces après « - », 3 après « 1. ».
    Python-Markdown n'imbrique qu'à 4 espaces : le prétraitement réindente les
    listes par multiples de 4, en gardant le décalage du code indenté.

    Python-Markdown découpe le texte en blocs aux lignes vides : une ligne vide
    est ajoutée avant un élément qui change de type de liste (Pandoc commence
    alors une autre liste), ou qui suit un paragraphe de suite d'un élément.

    Python-Markdown ne reconnaît que les blocs de code délimités en début de
    ligne, et ne prétraite pas le texte d'une citation : un bloc de code indenté
    sous un élément est mis de côté ici (#489), et les listes d'une citation sont
    prétraitées comme les autres (#490).

    Les marqueurs de Pandoc que Python-Markdown ne connaît pas (#325 : `a.`, `i)`,
    `(1)`, `#.`, `(@)`…) sont réécrits en `N.` ; le type de la liste (lettres,
    chiffres romains) est noté par une balise devant le texte du premier élément,
    que `ListTypeTreeprocessor` lit pour poser l'attribut `type` du `<ol>`.
    """

    def extendMarkdown(self, md: markdown.Markdown) -> None:
        # Après fenced_code (25) : un bloc de code délimité est déjà mis de côté.
        md.preprocessors.register(PandocListsPreprocessor(md), "pandoc_lists", 24)
        # Remplace le processeur de Python-Markdown, à la même priorité.
        md.parser.blockprocessors.register(
            DedentedItemsProcessor(md.parser), "indent", 90
        )
        # Après le traitement du texte en ligne (20), avant la mise en forme (10)
        # et les cases à cocher (-1), qui lisent le début du texte de l'élément.
        md.treeprocessors.register(ListTypeTreeprocessor(md), "list_type", 12)


# Balise, devant le texte du premier élément d'une liste, qui porte son type : un
# caractère de l'usage privé, que le texte d'une note ne contient pas.
LIST_TYPE_TAG = "{}"
LIST_TYPE_REGEX = re.compile("^(?P<type>[aAiI])")
# Classe qui porte l'affichage de chaque type de liste (voir style.css).
LIST_TYPE_CLASSES = {
    "a": "list-lower-alpha",
    "A": "list-upper-alpha",
    "i": "list-lower-roman",
    "I": "list-upper-roman",
}


class ListTypeTreeprocessor(markdown.treeprocessors.Treeprocessor):
    def run(self, root: etree.Element) -> None:
        for element in root.iter("ol"):
            first = next((child for child in element if child.tag == "li"), None)
            if first is None:
                continue
            target = first
            if not (first.text or "").strip() and len(first) and first[0].tag == "p":
                target = first[0]
            tag = LIST_TYPE_REGEX.match(target.text or "")
            if tag:
                element.set("type", tag.group("type"))
                element.set("class", LIST_TYPE_CLASSES[tag.group("type")])
                target.text = (target.text or "")[tag.end() :]


class PandocListsPreprocessor(markdown.preprocessors.Preprocessor):
    def run(self, lines: list[str]) -> list[str]:
        # Éléments `(@)` déjà rencontrés : leur numéro continue d'une liste à
        # l'autre, citations comprises.
        self.examples = 0
        return self.reindent(lines)

    def reindent(self, lines: list[str]) -> list[str]:
        # Éléments ouverts, du plus extérieur au plus intérieur : colonne de leur
        # texte et marqueur. Un élément de niveau n s'écrit avec 4 × n espaces.
        items: list[tuple[int, Marker]] = []
        previous_blank = True
        # Une liste peut suivre un titre sans ligne vide, mais pas un paragraphe.
        after_heading = False
        in_paragraph_after_blank = False
        result: list[str] = []

        index = 0
        while index < len(lines):
            line = lines[index]
            index += 1
            if not line.strip():
                result.append(line)
                previous_blank = True
                after_heading = False
                continue

            indent = len(line) - len(line.lstrip(" "))
            # Niveau de la ligne : nombre d'éléments ouverts dont elle atteint le
            # texte. Les colonnes croissent de l'extérieur vers l'intérieur.
            depth = sum(1 for column, _ in items if indent >= column)
            container = items[depth - 1][0] if depth else 0

            if not depth and (previous_blank or not items) and QUOTE_REGEX.match(line):
                # Citation : ses lignes, sans leur préfixe, sont prétraitées à part.
                end = index
                while end < len(lines) and QUOTE_REGEX.match(lines[end]):
                    end += 1
                quoted = [QUOTE_REGEX.sub("", text) for text in lines[index - 1 : end]]
                result.extend(f"> {text}".rstrip() for text in self.reindent(quoted))
                index = end
                items = []
                previous_blank = after_heading = in_paragraph_after_blank = False
                continue

            fence = FENCE_REGEX.match(line, indent)
            closing = closing_fence(lines, index, fence) if fence else None
            if fence and closing is not None and indent < container + MARKDOWN_INDENT:
                # Bloc de code délimité dans l'élément : mis de côté par l'extension
                # `fenced_code`, sans l'indentation de sa clôture.
                code = [dedent(text, indent) for text in lines[index - 1 : closing + 1]]
                stashed = self.md.preprocessors["fenced_code_block"].run(code)
                # Les lignes vides ajoutées autour du bloc aéreraient la liste.
                stashed = "\n".join(stashed).strip("\n").split("\n")
                items = items[:depth]
                margin = " " * (MARKDOWN_INDENT * depth)
                if not depth:
                    # Hors d'un élément, le bloc ne doit pas finir dans un paragraphe.
                    # Une ligne vide en tête d'une citation en ferait un, elle aussi.
                    before = [""] if result and not previous_blank else []
                    after = [""] if closing + 1 < len(lines) else []
                    stashed = [*before, *stashed, *after]
                result.extend(margin + text if text else text for text in stashed)
                index = closing + 1
                in_paragraph_after_blank = bool(depth) and (
                    in_paragraph_after_blank or previous_blank
                )
                previous_blank = after_heading = False
                continue
            sibling = items[depth] if depth < len(items) else None
            # Le marqueur de l'élément précédent de la liste décide des lettres
            # ambiguës : `i.` suit `b.` dans une liste de lettres.
            context = sibling[1] if sibling else None
            item = LIST_ITEM_REGEX.match(line, context)
            marker = (
                parse_marker(item.group("marker"), item.group("space"), context)
                if item
                else None
            )
            if (
                marker
                and not marker.native
                and not (previous_blank or after_heading or items)
            ):
                # Comme dans Pandoc, une liste ne peut pas interrompre un paragraphe :
                # `a.` reste du texte, et `#.` ne doit pas devenir un titre.
                if marker.kind == "auto":
                    line = line[:indent] + "\\" + line[indent:]
                item = marker = None
            # À 4 espaces au-delà du texte du parent, un marqueur n'ouvre plus
            # d'élément : la ligne est du code, ou la suite du texte précédent.
            if item and marker and indent < container + MARKDOWN_INDENT:
                items = items[:depth]
                new_list = sibling is not None and sibling[1].style != marker.style
                if sibling and new_list and sibling[1].ordered and marker.ordered:
                    # Deux listes numérotées qui se suivent : Python-Markdown n'en
                    # fait qu'une, même séparée par une ligne vide. Un commentaire
                    # (retiré au filtrage du HTML) les sépare.
                    if not previous_blank:
                        result.append("")
                    result.append(" " * (MARKDOWN_INDENT * depth) + "<!-- -->")
                    result.append("")
                elif (new_list or in_paragraph_after_blank) and not previous_blank:
                    result.append("")
                if marker.kind == "example":
                    self.examples += 1
                text = line[indent:]
                if not marker.native:
                    first = sibling is None or new_list
                    number = self.examples if marker.kind == "example" else marker.value
                    tag = ""
                    if first and marker.kind in ("alpha", "roman"):
                        tag = LIST_TYPE_TAG.format(marker.list_type)
                    text = f"{number}. {tag}{line[item.end() :]}"
                result.append(" " * (MARKDOWN_INDENT * depth) + text)
                items.append((text_column(item), marker))
                in_paragraph_after_blank = False
            else:
                if item and items and not previous_blank:
                    # Suite du texte de l'élément : le marqueur reste du texte.
                    line = escape_list_marker(item, line)
                if depth:
                    shift = MARKDOWN_INDENT * depth + indent - container
                    result.append(" " * shift + line[indent:])
                    in_paragraph_after_blank = (
                        in_paragraph_after_blank or previous_blank
                    )
                else:
                    # Ligne qui suit le texte de l'élément (continuation paresseuse),
                    # ou qui ferme les listes après une ligne vide ou en titre.
                    heading = ATX_HEADING_REGEX.match(line)
                    if heading and items and not previous_blank:
                        # Sans ligne vide, Python-Markdown lirait le titre dans le
                        # paragraphe de suite de l'élément (#491).
                        result.append("")
                    if previous_blank or heading:
                        items = []
                        in_paragraph_after_blank = False
                    result.append(line)
            previous_blank = False
            after_heading = bool(ATX_HEADING_REGEX.match(line))

        return result


class DedentedItemsProcessor(ListIndentProcessor):
    """Découpe un bloc qui commence dans une sous-liste et en sort (#482).

    Python-Markdown place tout un bloc (des lignes sans ligne vide) au niveau de sa
    première ligne : dans « 1. x / (vide) / - t1 / 2. t4 », `2. t4` était lu dans la
    sous-liste de `t1`. Chaque élément moins indenté que ceux qui le précèdent est
    ici ajouté à la liste de son niveau.

    Ajouter une ligne vide devant lui ne suffirait pas : elle aérerait toujours la
    liste. Pour Pandoc, une ligne vide entre deux sous-éléments n'aère que la
    sous-liste : l'élément n'est dans un `<p>` que si la liste en a déjà.
    """

    def run(self, parent: etree.Element, blocks: list[str]) -> None:
        parts = split_dedented_items(blocks[0])
        level, sibling = self.get_level(parent, blocks[0])
        if (
            len(parts) < 2
            or level != parts[0][0]
            or self.parser.state.isstate("list")
            or parent.tag in self.LIST_TYPES
        ):
            super().run(parent, blocks)
            return

        blocks.pop(0)
        # Le texte de l'élément parent n'est mis dans un `<p>` que si la ligne vide le
        # suit : pas si le bloc continue une sous-liste.
        item = self.lastChild(sibling)
        child = self.lastChild(item) if item is not None else None
        text = None
        if item is not None and child is not None and child.tag in self.LIST_TYPES:
            text, item.text = item.text, None
        super().run(parent, [parts[0][1]])
        if item is not None and text:
            item.text = text

        for index, (part_level, part) in enumerate(parts[1:], start=1):
            target = None if part_level is None else self.list_at(parent, part_level)
            if part_level is None or target is None:
                # Fin de la liste, ou pas de liste à ce niveau : la suite est lue
                # comme un autre bloc.
                blocks.insert(0, "\n".join(text for _, text in parts[index:]))
                return
            self.add_items(target, self.looseDetab(part, part_level))

    def list_at(self, parent: etree.Element, level: int) -> etree.Element | None:
        """Dernière liste de `parent` au niveau donné, si elle est encore ouverte."""
        found = None
        for _ in range(level + 1):
            found = self.lastChild(parent)
            if found is None or found.tag not in self.LIST_TYPES or not len(found):
                return None
            parent = found[-1]
        return found

    def add_items(self, target: etree.Element, block: str) -> None:
        loose = any(child.tag == "p" for item in target for child in item)
        known = len(target)
        # Avec une liste pour parent, le processeur y ajoute les éléments, sans `<p>`.
        name = "olist" if target.tag == "ol" else "ulist"
        self.parser.blockprocessors[name].run(target, [block])
        for item in target[known:]:
            if loose and item.text:
                paragraph = etree.Element("p")
                paragraph.text, item.text = item.text, ""
                item.insert(0, paragraph)


def split_dedented_items(block: str) -> list[tuple[int | None, str]]:
    """Découpe un bloc avant chaque élément moins indenté que les précédents.

    Renvoie chaque partie avec le niveau de son premier élément. Un titre ou un trait
    horizontal termine la liste : la dernière partie, sans niveau, commence là. Le bloc
    entier, sans niveau, s'il ne commence pas par un élément.
    """
    lines = block.split("\n")
    first = BLOCK_ITEM_REGEX.match(lines[0])
    if not first:
        return [(None, block)]
    level = len(first["indent"]) // MARKDOWN_INDENT
    parts: list[tuple[int | None, str]] = []
    start = 0
    for index, line in enumerate(lines):
        item = BLOCK_ITEM_REGEX.match(line)
        if BLOCK_END_REGEX.match(line):
            parts.append((level, "\n".join(lines[start:index])))
            return [*parts, (None, "\n".join(lines[index:]))]
        item_level = len(item["indent"]) // MARKDOWN_INDENT if item else level
        if item_level < level:
            parts.append((level, "\n".join(lines[start:index])))
            start, level = index, item_level
    return [*parts, (level, "\n".join(lines[start:]))]


def closing_fence(lines: list[str], start: int, fence: re.Match[str]) -> int | None:
    """Indice de la ligne qui ferme le bloc de code ouvert par `fence`, à partir de
    `start` : la même clôture, au moins aussi longue, seule sur sa ligne."""
    opening = fence["fence"]
    for index in range(start, len(lines)):
        text = lines[index].strip()
        if text.startswith(opening) and not text.strip(opening[0]):
            return index
    return None


def dedent(line: str, columns: int) -> str:
    """La ligne sans ses `columns` premières espaces, au plus."""
    return line[min(columns, len(line) - len(line.lstrip(" "))) :]


def escape_list_marker(item: re.Match[str], line: str) -> str:
    """Échappe le marqueur de liste d'une ligne : « 1\\. » ou « \\- »."""
    marker = item.group("marker")
    if marker[0] == "#":
        # `#.` serait pris pour un titre : c'est le dièse qu'on échappe.
        return line[: item.start("marker")] + "\\" + line[item.start("marker") :]
    escaped = f"{marker[:-1]}\\{marker[-1]}"
    return line[: item.start("marker")] + escaped + line[item.end("marker") :]


# Case en tête d'un élément de liste, suivie d'un blanc sur la même ligne.
TASK_REGEX = re.compile(r"^\[(?P<mark>[ xX])\][ \t]+")
# Balises qui terminent le libellé d'une case : le texte d'un élément s'arrête
# à la première d'entre elles (sous-liste, paragraphe suivant, code…).
BLOCK_TAGS = {
    *("p", "ul", "ol", "pre", "blockquote", "table", "div", "hr", "dl"),
    *("h1", "h2", "h3", "h4", "h5", "h6"),
}


class TaskListExtension(markdown.Extension):
    """Cases à cocher « - [ ] » et « - [x] », comme dans Quarto (#231).

    Comme Pandoc, le texte de l'élément est placé dans un `<label>`, et une
    liste à puces dont tous les éléments sont des cases reçoit la classe
    `task-list`. Le libellé commence par « [ ] » ou « [x] », que `task_checkboxes`
    remplace par la case après le filtrage du HTML.
    """

    def extendMarkdown(self, md: markdown.Markdown) -> None:
        # Après unescape (0) : « \[ ] » est aussi une case, comme dans Pandoc.
        md.treeprocessors.register(TaskListTreeprocessor(md), "task_list", -1)


class TaskListTreeprocessor(markdown.treeprocessors.Treeprocessor):
    def run(self, root: etree.Element) -> None:
        lists = [element for element in root.iter() if element.tag in ("ul", "ol")]
        for element in lists:
            items = [child for child in element if child.tag == "li"]
            tasks = [label_task(item) for item in items]
            if element.tag == "ul" and items and all(tasks):
                element.set("class", "task-list")


def label_task(item: etree.Element) -> bool:
    """Place le texte d'un élément commençant par une case dans un `<label>`.

    Dans une liste lâche, le texte est celui du premier paragraphe.
    """
    target = item
    if not (item.text or "").strip() and len(item) and item[0].tag == "p":
        target = item[0]
    task = TASK_REGEX.match(target.text or "")
    if not task:
        return False

    label = etree.Element("label")
    mark = "x" if task.group("mark") in "xX" else " "
    label.text = f"[{mark}]" + (target.text or "")[task.end() :]
    for child in list(target):
        if child.tag in BLOCK_TAGS:
            break
        target.remove(child)
        label.append(child)
    target.text = None
    target.insert(0, label)
    return True


# Début du libellé d'une case, une fois le HTML filtré.
TASK_LABEL_REGEX = re.compile(r"<label>\[(?P<mark>[ x])\]")


def task_checkboxes(html: str) -> str:
    """Remplace le début du libellé des cases par une case désactivée (#231).

    Appliqué au HTML filtré, qui n'accepte pas de champ de formulaire. La case
    est désactivée : la page affiche la note, elle ne la modifie pas.
    """

    def repl(match: re.Match[str]) -> str:
        checked = " checked" if match.group("mark") == "x" else ""
        return f'<label><input type="checkbox"{checked} disabled>'

    return TASK_LABEL_REGEX.sub(repl, html)
