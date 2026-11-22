"""Filtrage du HTML rendu (liste blanche nh3) et retouches du HTML filtré."""

import re

import nh3

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
IMG_TAG_REGEX = re.compile(r"<img\b")
IMG_PERCENT_WIDTH_REGEX = re.compile(
    r'(?<=<img )([^>]*?)width="(?P<width>\d+(?:\.\d+)?%)"'
)

ALLOWED_URL_SCHEMES = {"http", "https", "mailto"}
# Alignement des colonnes de tableau, produit par l'extension tables.
ALLOWED_STYLE_PROPERTIES = {"text-align"}


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


def lazy_images(html: str) -> str:
    """Images chargées et décodées à la demande, près de l'écran (#225).

    Appliqué au HTML filtré : `<img` n'y est que le début d'une balise.
    """
    html = IMG_TAG_REGEX.sub('<img loading="lazy" decoding="async"', html)
    # `{width=80%}` de Quarto : l'attribut width n'accepte que des pixels (#259).
    return IMG_PERCENT_WIDTH_REGEX.sub(r'\1style="width: \g<width>"', html)
