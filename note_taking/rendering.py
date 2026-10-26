"""Rendu HTML des notes : Markdown et références d'images."""

import re
import xml.etree.ElementTree as etree
from pathlib import PurePosixPath

import markdown
import nh3
from django.templatetags.static import static
from django.utils.html import escape

from core.icons import icon_svg
from images.models import Image

from .qmd.lists import LIST_ITEM_REGEX, text_column
from .qmd.parser import BLOCK_END, METADATA_BLOCK_START


class NoSetextHeadingsExtension(markdown.Extension):
    """Désactive les titres « setext » (texte souligné de - ou de =).

    Les notes n'utilisent que les titres en #, sur lesquels repose le découpage en
    note parts. Sans cela, un élément de liste vide (« - ») après un élément de
    liste ferait de celui-ci un titre, là où Quarto affiche une liste (#124).
    """

    def extendMarkdown(self, md: markdown.Markdown) -> None:
        md.parser.blockprocessors.deregister("setextheader")


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
    """

    def extendMarkdown(self, md: markdown.Markdown) -> None:
        # Après fenced_code (25) : un bloc de code délimité est déjà mis de côté.
        md.preprocessors.register(PandocListsPreprocessor(md), "pandoc_lists", 24)


class PandocListsPreprocessor(markdown.preprocessors.Preprocessor):
    def run(self, lines: list[str]) -> list[str]:
        # Éléments ouverts, du plus extérieur au plus intérieur : colonne de leur
        # texte et type de liste. Un élément de niveau n s'écrit avec 4 × n espaces.
        items: list[tuple[int, bool]] = []
        previous_blank = True
        in_paragraph_after_blank = False
        result = []

        for line in lines:
            if not line.strip():
                result.append(line)
                previous_blank = True
                continue

            indent = len(line) - len(line.lstrip(" "))
            # Niveau de la ligne : nombre d'éléments ouverts dont elle atteint le
            # texte. Les colonnes croissent de l'extérieur vers l'intérieur.
            depth = sum(1 for column, _ in items if indent >= column)
            container = items[depth - 1][0] if depth else 0
            item = LIST_ITEM_REGEX.match(line)
            # À 4 espaces au-delà du texte du parent, un marqueur n'ouvre plus
            # d'élément : la ligne est du code, ou la suite du texte précédent.
            if item and indent < container + MARKDOWN_INDENT:
                sibling = items[depth] if depth < len(items) else None
                items = items[:depth]
                ordered = item.group("marker")[0].isdigit()
                new_list = sibling is not None and sibling[1] != ordered
                if (new_list or in_paragraph_after_blank) and not previous_blank:
                    result.append("")
                result.append(" " * (MARKDOWN_INDENT * depth) + line[indent:])
                items.append((text_column(item), ordered))
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

        return result


def escape_list_marker(item: re.Match[str], line: str) -> str:
    """Échappe le marqueur de liste d'une ligne : « 1\\. » ou « \\- »."""
    marker = item.group("marker")
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
]

IMAGE_MISSING_PATH = "note_taking/img/image-missing.svg"

# Image telle qu'écrite dans une note : ![légende](chemin/vers/image.png)
IMAGE_PATH_REGEX = re.compile(r"\!\[[^\]]*\]\((?P<path>[^)]+)\)")

# Image référencée en base après analyse : ![légende](image:<pk>){attributs}
IMAGE_REF_REGEX = re.compile(
    r"\!\[(?P<alt>[^\]]*)\]\(image:(?P<pk>\d+)\)(?P<attrs>\{[^}]*\})?"
)

# Balise de titre ouvrante ou fermante du HTML rendu : <h2 …> ou </h2>.
HEADING_TAG_REGEX = re.compile(r"<(?P<slash>/?)h(?P<level>[1-6])\b")

# Image désignée par une URL complète ou absolue : pas une image importée.
EXTERNAL_URL_REGEX = re.compile(r"^([a-z][a-z0-9+.-]*://|/|data:)", re.IGNORECASE)

# Image sur un autre serveur, avec son titre et ses attributs éventuels :
# ![légende](https://…/a.png "titre"){width=50%}. Elle n'est pas chargée (#220).
REMOTE_IMAGE_REGEX = re.compile(
    r"\!\[(?P<alt>[^\]]*)\]\((?P<url>[a-z][a-z0-9+.-]*://[^)\s]+)"
    r"(?:\s+\"[^\"]*\")?\)(?:\{[^}]*\})?",
    re.IGNORECASE,
)


# Callout Quarto : ::: {.callout-<type> title="…"} … :::
CALLOUT_START_REGEX = re.compile(r"^:::\s*\{\.callout-(?P<type>\w+)(?P<attrs>[^}]*)\}$")
CALLOUT_TITLE_ATTR_REGEX = re.compile(r'title="(?P<title>[^"]*)"')
CALLOUT_HEADING_REGEX = re.compile(r"^#+\s+(?P<title>.+)$")

# Blocs Quarto ::: {…} … :::, éventuellement imbriqués
DIV_START_REGEX = re.compile(r"^:::+\s*\{[^}]*\}$")
DIV_END_REGEX = re.compile(r"^:::+$")
DIV_ID_REGEX = re.compile(r"#(?P<id>[\w-]+)")

# Figure en colonnes : ::: {#fig-… layout-ncol=N} … légende :::
LAYOUT_START_REGEX = re.compile(
    r"^:::\s*\{(?P<attrs>[^}]*\blayout-ncol=(?P<ncol>\d+)[^}]*)\}$"
)
# Classes Tailwind écrites en entier, pour qu'un build puisse les détecter.
LAYOUT_GRID_CLASSES = {
    1: "grid-cols-1",
    2: "grid-cols-2",
    3: "grid-cols-3",
    4: "grid-cols-4",
    5: "grid-cols-5",
    6: "grid-cols-6",
}

# Colonnes : ::: {.columns} ::: {.column width="40%"} … ::: :::
COLUMNS_START_REGEX = re.compile(r"^:::\s*\{\.columns\}$")
COLUMN_START_REGEX = re.compile(r"^:::\s*\{\.column(?P<attrs>[^}]*)\}$")
COLUMN_WIDTH_REGEX = re.compile(r'width="?(?P<width>\d+(?:\.\d+)?%)"?')

# Titres par défaut de Quarto en français
CALLOUT_DEFAULT_TITLES = {
    "note": "Note",
    "tip": "Astuce",
    "warning": "Avertissement",
    "caution": "Attention",
    "important": "Important",
}

# Icônes Material Symbols proches de celles de Quarto
CALLOUT_ICONS = {
    "note": "info",
    "tip": "lightbulb",
    "warning": "warning",
    "caution": "report",
    "important": "error",
}
CALLOUT_NO_ICON_ATTR_REGEX = re.compile(r"\bicon=false\b")

CODE_FENCE = "```"

# HTML gardé dans le contenu des notes (#241) : celui d'un document, sans script,
# formulaire, cadre ni style libre. Les chemins relatifs restent autorisés.
ALLOWED_TAGS = {
    *("p", "br", "hr", "blockquote", "pre", "code", "kbd", "samp"),
    *("h1", "h2", "h3", "h4", "h5", "h6"),
    *("ul", "ol", "li", "dl", "dt", "dd"),
    *("table", "thead", "tbody", "tfoot", "tr", "th", "td", "caption"),
    *("a", "img", "figure", "figcaption", "div", "span", "details", "summary"),
    "label",
    *("em", "strong", "b", "i", "u", "s", "del", "ins", "mark", "small"),
    *("sub", "sup", "abbr"),
}
ALLOWED_ATTRIBUTES = {
    "*": {"class", "id", "title"},
    "a": {"href"},
    "img": {"src", "alt", "width", "height"},
    "ol": {"start"},
    "th": {"style", "colspan", "rowspan"},
    "td": {"style", "colspan", "rowspan"},
}
IMG_TAG_REGEX = re.compile(r"<img\b")
IMG_PERCENT_WIDTH_REGEX = re.compile(
    r'(?<=<img )([^>]*?)width="(?P<width>\d+(?:\.\d+)?%)"'
)

ALLOWED_URL_SCHEMES = {"http", "https", "mailto"}
# Alignement des colonnes de tableau, produit par l'extension tables.
ALLOWED_STYLE_PROPERTIES = {"text-align"}


def render_markdown(text: str) -> str:
    """Rend du Markdown en HTML, callouts et blocs de mise en page Quarto compris."""
    html: list[str] = []
    pending: list[str] = []
    lines = text.split("\n")
    in_code_block = False
    index = 0

    while index < len(lines):
        line = lines[index]
        stripped = line.strip()
        if stripped.startswith(CODE_FENCE):
            in_code_block = not in_code_block

        block = None if in_code_block else match_block_start(stripped)
        end = find_block_end(lines, index) if block else None
        if block and end is not None:
            start, render_block = block
            html.append(render_plain_markdown("\n".join(pending)))
            pending = []
            html.append(render_block(start, lines[index + 1 : end]))
            index = end + 1
            continue

        pending.append(line)
        index += 1

    html.append(render_plain_markdown("\n".join(pending)))
    return "\n".join(part for part in html if part)


def render_plain_markdown(text: str) -> str:
    """Markdown en HTML, filtré : tout ce qu'écrit l'utilisateur passe par ici.

    Le HTML des blocs Quarto (callouts, grilles, colonnes) est construit autour,
    à partir de valeurs échappées ou contrôlées, et n'a pas à être filtré.
    """
    html = sanitize_html(markdown.markdown(text, extensions=MARKDOWN_EXTENSIONS))
    return lazy_images(task_checkboxes(html))


def lazy_images(html: str) -> str:
    """Images chargées et décodées à la demande, près de l'écran (#225).

    Appliqué au HTML filtré : `<img` n'y est que le début d'une balise.
    """
    html = IMG_TAG_REGEX.sub('<img loading="lazy" decoding="async"', html)
    # `{width=80%}` de Quarto : l'attribut width n'accepte que des pixels (#259).
    return IMG_PERCENT_WIDTH_REGEX.sub(r'\1style="width: \g<width>"', html)


def sanitize_html(html: str) -> str:
    """Liste blanche de balises, d'attributs et de schémas d'URL (#241).

    Un script, un gestionnaire `on…` ou un lien `javascript:` écrit dans une
    note s'exécuterait dans la page et pourrait envoyer les notes ailleurs.
    """
    return nh3.clean(
        html,
        tags=ALLOWED_TAGS,
        attributes=ALLOWED_ATTRIBUTES,
        url_schemes=ALLOWED_URL_SCHEMES,
        filter_style_properties=ALLOWED_STYLE_PROPERTIES,
        link_rel=None,
    )


def match_block_start(line: str):
    """Début de bloc rendu à part (callout, figure, colonnes) et son rendu."""
    for regex, render_block in (
        (CALLOUT_START_REGEX, render_callout),
        (LAYOUT_START_REGEX, render_layout),
        (COLUMNS_START_REGEX, render_columns),
    ):
        start = regex.match(line)
        if start:
            return start, render_block
    return None


def find_block_end(lines: list[str], start: int) -> int | None:
    """Indice de la ligne fermant le bloc ouvert à `start`, s'il existe.

    Tient compte des blocs imbriqués ; les blocs de code sont ignorés.
    """
    depth = 1
    in_code_block = False
    for index in range(start + 1, len(lines)):
        stripped = lines[index].strip()
        if stripped.startswith(CODE_FENCE):
            in_code_block = not in_code_block
        elif in_code_block:
            continue
        elif DIV_START_REGEX.match(stripped):
            depth += 1
        elif DIV_END_REGEX.match(stripped):
            depth -= 1
            if depth == 0:
                return index
    return None


def split_blocks(lines: list[str]) -> list[str]:
    """Découpe en blocs séparés par des lignes vides, hors code et blocs `:::`."""
    blocks: list[list[str]] = [[]]
    depth = 0
    in_code_block = False
    for line in lines:
        stripped = line.strip()
        if stripped.startswith(CODE_FENCE):
            in_code_block = not in_code_block
        elif not in_code_block and DIV_START_REGEX.match(stripped):
            depth += 1
        elif not in_code_block and depth and DIV_END_REGEX.match(stripped):
            depth -= 1

        if not stripped and not in_code_block and depth == 0:
            blocks.append([])
        else:
            blocks[-1].append(line)
    return ["\n".join(block) for block in blocks if block]


def render_layout(start: re.Match[str], body: list[str]) -> str:
    """Blocs disposés en grille de N colonnes, à la manière de Quarto.

    Avec un identifiant `#fig-…`, le bloc est une figure et son dernier
    paragraphe, s'il n'est pas une image, en est la légende commune.
    """
    attrs = start.group("attrs")
    id_match = DIV_ID_REGEX.search(attrs)
    block_id = id_match.group("id") if id_match else None
    is_figure = bool(block_id and block_id.startswith("fig-"))

    cells = split_blocks(body)
    caption = None
    if is_figure and len(cells) > 1 and not cells[-1].lstrip().startswith("!["):
        caption = cells.pop()

    ncol = min(max(int(start.group("ncol")), 1), max(LAYOUT_GRID_CLASSES))
    tag = "figure" if is_figure else "div"
    id_attr = f' id="{escape(block_id)}"' if block_id else ""
    cells_html = "".join(
        f'<div class="min-w-0">{render_markdown(cell)}</div>' for cell in cells
    )
    caption_html = (
        '<figcaption class="mt-2 text-sm text-center text-slate-600">'
        f"{render_markdown(caption)}</figcaption>"
        if caption is not None
        else ""
    )

    return (
        f'<{tag} class="my-2"{id_attr}>'
        f'<div class="grid {LAYOUT_GRID_CLASSES[ncol]} gap-4 items-start">'
        f"{cells_html}</div>{caption_html}</{tag}>"
    )


def render_columns(start: re.Match[str], body: list[str]) -> str:
    """Colonnes côte à côte ; une colonne sans largeur occupe la place restante."""
    columns: list[tuple[str, list[str]]] = []
    stray: list[str] = []
    index = 0
    while index < len(body):
        column = COLUMN_START_REGEX.match(body[index].strip())
        end = find_block_end(body, index) if column else None
        if column and end is not None:
            if "".join(stray).strip():
                columns.append(("", stray))
            stray = []
            columns.append((column.group("attrs"), body[index + 1 : end]))
            index = end + 1
            continue
        stray.append(body[index])
        index += 1
    if "".join(stray).strip():
        columns.append(("", stray))

    columns_html = []
    for attrs, lines in columns:
        width = COLUMN_WIDTH_REGEX.search(attrs)
        opening = (
            f'<div class="min-w-0" style="flex: 0 1 {width.group("width")}">'
            if width
            else '<div class="flex-1 min-w-0">'
        )
        columns_html.append(f"{opening}{render_markdown('\n'.join(lines))}</div>")

    return f'<div class="flex gap-4 my-2">{"".join(columns_html)}</div>'


def render_callout(start: re.Match[str], body: list[str]) -> str:
    """Encadré à la manière de Quarto.

    Le titre est l'attribut `title`, sinon le premier titre Markdown du
    callout, sinon le titre par défaut du type. L'icône dépend du type et
    se retire avec `icon=false`.
    """
    callout_type = start.group("type")
    attrs = start.group("attrs")
    title_attr = CALLOUT_TITLE_ATTR_REGEX.search(attrs)
    body = list(body)

    if title_attr:
        title = title_attr.group("title")
    else:
        first = next((i for i, line in enumerate(body) if line.strip()), None)
        heading = (
            CALLOUT_HEADING_REGEX.match(body[first].strip())
            if first is not None
            else None
        )
        if first is not None and heading:
            title = heading.group("title").strip()
            del body[first]
        else:
            title = CALLOUT_DEFAULT_TITLES.get(callout_type, callout_type.capitalize())

    icon = CALLOUT_ICONS.get(callout_type)
    icon_html = (
        icon_svg(icon, "callout-icon")
        if icon and not CALLOUT_NO_ICON_ATTR_REGEX.search(attrs)
        else ""
    )

    return (
        f'<div class="callout callout-{callout_type}">'
        f'<div class="callout-header">{icon_html}'
        f'<span class="callout-title">{escape(title)}</span></div>'
        f'<div class="callout-body">{render_markdown("\n".join(body))}</div>'
        "</div>"
    )


def resolve_image_refs(content: str) -> str:
    """Remplace les références `image:<pk>` par l'URL du fichier de l'image."""

    def repl(match: re.Match[str]) -> str:
        alt = match.group("alt")
        attrs = match.group("attrs") or ""

        try:
            url = Image.objects.get(pk=match.group("pk")).file.url
        except Image.DoesNotExist:
            url = static(IMAGE_MISSING_PATH)

        return f"![{alt}]({url}){attrs}"

    return IMAGE_REF_REGEX.sub(repl, content)


def render_note_part(content: str) -> str:
    return render_markdown(remote_images_as_links(resolve_image_refs(content)))


def render_note_body(body: str) -> str:
    """Rend le body complet d'une note, tel qu'écrit dans le fichier qmd.

    Les titres sont décalés d'un niveau (# devient h2) : la page qui l'affiche
    a son propre h1.
    """
    html = render_markdown(
        remote_images_as_links(resolve_image_paths(strip_metadata_blocks(body)))
    )
    return HEADING_TAG_REGEX.sub(shift_heading, html)


def shift_heading(match: re.Match[str]) -> str:
    level = min(int(match.group("level")) + 1, 6)
    return f"<{match.group('slash')}h{level}"


def strip_metadata_blocks(text: str) -> str:
    """Retire les blocs `::: {.metadata}`, lus à l'analyse mais pas affichés."""
    kept: list[str] = []
    in_code_block = False
    in_metadata_block = False

    for line in text.split("\n"):
        stripped = line.strip()
        if stripped.startswith(CODE_FENCE) and not in_metadata_block:
            in_code_block = not in_code_block

        if in_metadata_block:
            in_metadata_block = stripped != BLOCK_END
        elif not in_code_block and stripped == METADATA_BLOCK_START:
            in_metadata_block = True
        else:
            kept.append(line)

    return "\n".join(kept)


def resolve_image_paths(content: str) -> str:
    """Remplace les chemins d'images par l'URL de l'image importée de même nom.

    Une image inconnue est remplacée par l'image de remplacement ; une URL
    externe est conservée.
    """

    def repl(match: re.Match[str]) -> str:
        path = match.group("path")
        name = image_name(path)
        if name is None:
            return match.group(0)

        image = Image.objects.filter(name=name).first()
        url = image.file.url if image else static(IMAGE_MISSING_PATH)
        return match.group(0).replace(path, url)

    return IMAGE_PATH_REGEX.sub(repl, content)


def image_name(path: str) -> str | None:
    """Nom de l'image importée désignée par un chemin, ou None pour une URL externe.

    Seul le nom de fichier compte, quel que soit le dossier, écrit avec / ou \\.
    Règle commune à l'analyse, au rendu et à l'export (#220).
    """
    if EXTERNAL_URL_REGEX.match(path):
        return None
    return PurePosixPath(path.replace("\\", "/")).name


def remote_images_as_links(content: str) -> str:
    """Remplace chaque image sur un autre serveur par un lien vers son adresse.

    Les notes sont privées : le navigateur ne contacte aucun serveur tiers (#220).
    Le texte du lien est la légende, ou l'adresse sans légende.
    """

    def repl(match: re.Match[str]) -> str:
        url = match.group("url")
        return f"[{match.group('alt') or url}]({url})"

    return REMOTE_IMAGE_REGEX.sub(repl, content)
