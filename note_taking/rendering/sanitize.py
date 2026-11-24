"""Filtrage du HTML rendu (liste blanche nh3) et retouches du HTML filtré."""

import html as html_module
import re

import nh3
from django.utils.html import escape

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
    "ol": {"start", "type"},
    "th": {"style", "colspan", "rowspan"},
    "td": {"style", "colspan", "rowspan"},
}
# Dans le HTML filtré : début ou fin d'un lien, image. Une valeur d'attribut peut contenir
# « > ».
LINK_OR_IMAGE_REGEX = re.compile(
    r"(?P<link><a(?=[\s>]))|(?P<link_end></a>)"
    r'|<img(?P<attrs>(?:\s+[\w-]+(?:="[^"]*")?)*)\s*/?>'
)
SRC_REGEX = re.compile(r'\ssrc="(?P<value>[^"]*)"')
ALT_REGEX = re.compile(r'\salt="(?P<value>[^"]*)"')
# Caractères d'une adresse que le navigateur ignore : blancs et contrôles aux bords,
# tabulations et fins de ligne partout.
URL_EDGES = "".join(map(chr, range(0x21)))
URL_IGNORED_REGEX = re.compile(r"[\t\n\r]")
URL_SCHEME_REGEX = re.compile(r"[a-z][a-z0-9+.-]*:", re.IGNORECASE)

IMG_TAG_REGEX = re.compile(r"<img\b")
TABLE_START_REGEX = re.compile(r"<table\b")
TABLE_END_REGEX = re.compile(r"</table>")
IMG_PERCENT_WIDTH_REGEX = re.compile(
    r'(?<=<img )([^>]*?)width="(?P<width>\d+(?:\.\d+)?%)"'
)

ALLOWED_URL_SCHEMES = {"http", "https", "mailto"}
# Alignement des colonnes de tableau, produit par l'extension tables.
ALLOWED_STYLE_PROPERTIES = {"text-align"}


def sanitize_html(html: str) -> str:
    """Liste blanche de balises, d'attributs et de schémas d'URL (#241).

    Un script, un gestionnaire `on…` ou un lien `javascript:` écrit dans une
    note s'exécuterait dans la page et pourrait envoyer les notes ailleurs. Aucune
    image d'un autre serveur n'en ressort (`remote_images_as_text`).
    """
    cleaned = nh3.clean(
        html,
        tags=ALLOWED_TAGS,
        attributes=ALLOWED_ATTRIBUTES,
        url_schemes=ALLOWED_URL_SCHEMES,
        filter_style_properties=ALLOWED_STYLE_PROPERTIES,
        link_rel=None,
    )
    return remote_images_as_text(cleaned)


def is_remote(url: str) -> bool:
    """L'adresse d'une image mène hors de l'application, comme le navigateur la lit."""
    url = URL_IGNORED_REGEX.sub("", url.strip(URL_EDGES)).replace("\\", "/")
    return url.startswith("//") or bool(URL_SCHEME_REGEX.match(url))


def remote_images_as_text(html: str) -> str:
    """Remplace chaque image d'un autre serveur par un lien vers son adresse (#458).

    Le navigateur ne contacte aucun serveur tiers (#220), quelle que soit la façon
    d'écrire l'image. Dans un lien, qui n'en contient pas d'autre, il ne reste que le
    texte de l'image : son `alt`, ou son adresse.
    """
    in_link = False

    def repl(match: re.Match[str]) -> str:
        nonlocal in_link
        if match["link"] or match["link_end"]:
            in_link = bool(match["link"])
            return match[0]
        src = SRC_REGEX.search(match["attrs"])
        url = html_module.unescape(src["value"]) if src else ""
        if not is_remote(url):
            return match[0]
        alt = ALT_REGEX.search(match["attrs"])
        text = escape(html_module.unescape(alt["value"]).strip() if alt else "")
        text = text or escape(url)
        return text if in_link else f'<a href="{escape(url)}">{text}</a>'

    return LINK_OR_IMAGE_REGEX.sub(repl, html)


def scrollable_tables(html: str) -> str:
    """Chaque tableau dans un bloc qui défile seul s'il est trop large (#421).

    Appliqué au HTML filtré : `<table` n'y est que le début d'une balise, refermée.
    """
    return TABLE_END_REGEX.sub(
        "</table></div>",
        TABLE_START_REGEX.sub('<div class="table-scroll"><table', html),
    )


def lazy_images(html: str) -> str:
    """Images chargées et décodées à la demande, près de l'écran (#225).

    Appliqué au HTML filtré : `<img` n'y est que le début d'une balise.
    """
    html = IMG_TAG_REGEX.sub('<img loading="lazy" decoding="async"', html)
    # `{width=80%}` de Quarto : l'attribut width n'accepte que des pixels (#259).
    return IMG_PERCENT_WIDTH_REGEX.sub(r'\1style="width: \g<width>"', html)
