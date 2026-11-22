"""Listes de Pandoc dans Python-Markdown : imbrication, marqueurs, cases."""

import re
import xml.etree.ElementTree as etree

import markdown

from ..qmd.lists import LIST_ITEM_REGEX, Marker, parse_marker, text_column

ATX_HEADING_REGEX = re.compile(r"^#{1,6}(\s|$)")
# Pas d'indentation de Python-Markdown : un niveau de liste, un bloc de code.
MARKDOWN_INDENT = 4


class PandocListsExtension(markdown.Extension):
    """Imbrique les listes selon la règle de Pandoc, celle de Quarto (#229).

    Pour Pandoc, un élément est imbriqué si son marqueur commence au moins à la
    colonne du texte de l'élément parent : 2 espaces après « - », 3 après « 1. ».
    Python-Markdown n'imbrique qu'à 4 espaces : le prétraitement réindente les
    listes par multiples de 4, en gardant le décalage du code indenté.

    Python-Markdown découpe le texte en blocs aux lignes vides : une ligne vide
    est ajoutée avant un élément qui change de type de liste (Pandoc commence
    alors une autre liste), ou qui suit un paragraphe de suite d'un élément.

    Les marqueurs de Pandoc que Python-Markdown ne connaît pas (#325 : `a.`, `i)`,
    `(1)`, `#.`, `(@)`…) sont réécrits en `N.` ; le type de la liste (lettres,
    chiffres romains) est noté par une balise devant le texte du premier élément,
    que `ListTypeTreeprocessor` lit pour poser l'attribut `type` du `<ol>`.
    """

    def extendMarkdown(self, md: markdown.Markdown) -> None:
        # Après fenced_code (25) : un bloc de code délimité est déjà mis de côté.
        md.preprocessors.register(PandocListsPreprocessor(md), "pandoc_lists", 24)
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
        # Éléments ouverts, du plus extérieur au plus intérieur : colonne de leur
        # texte et marqueur. Un élément de niveau n s'écrit avec 4 × n espaces.
        items: list[tuple[int, Marker]] = []
        previous_blank = True
        # Une liste peut suivre un titre sans ligne vide, mais pas un paragraphe.
        after_heading = False
        in_paragraph_after_blank = False
        # Éléments `(@)` déjà rencontrés : leur numéro continue d'une liste à l'autre.
        examples = 0
        result = []

        for line in lines:
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
                    examples += 1
                text = line[indent:]
                if not marker.native:
                    first = sibling is None or new_list
                    number = examples if marker.kind == "example" else marker.value
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
                    if previous_blank or ATX_HEADING_REGEX.match(line):
                        items = []
                        in_paragraph_after_blank = False
                    result.append(line)
            previous_blank = False
            after_heading = bool(ATX_HEADING_REGEX.match(line))

        return result


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
