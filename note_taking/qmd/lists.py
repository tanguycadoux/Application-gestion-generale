"""Listes selon Pandoc, celui de Quarto : imbrication (#229) et marqueurs (#325).

Un élément est imbriqué si son marqueur commence au moins à la colonne du texte
de l'élément parent : 2 espaces après « - », 3 après « 1. ». Le rendu des notes
et les sous-tâches issues des notes (#238) suivent cette même règle.

Les marqueurs sont ceux de l'extension `fancy_lists` de Pandoc, active par défaut dans
le Markdown de Quarto (vérifié avec Pandoc 3.10 et `quarto render` 1.10.19) :

- puces `-`, `*`, `+` ;
- nombres `1.`, `1)`, `(1)` ;
- lettres `a.`, `A)`, `(a)` : **une seule lettre** ;
- chiffres romains `i.`, `ii.`, `iv)`, `(IX)` : `i` ou `I` seul, ou plusieurs lettres ;
- numérotation automatique `#.`, `#)` ;
- exemples numérotés `(@)`, `(@étiquette)`.
"""

import re
from dataclasses import dataclass

# Élément de liste, avant validation : indentation, marqueur, espaces avant le texte.
_ITEM_PATTERN = re.compile(
    r"^(?P<indent> *)"
    r"(?P<marker>[-*+]"
    r"|(?:\d+|[A-Za-z]+|#)[.)]"
    r"|\((?:\d+|[A-Za-z]+|@[\w-]*)\))"
    r"(?P<space> +|$)"
)
# À 4 espaces au-delà du texte du parent, un marqueur n'ouvre plus d'élément :
# la ligne est du code, ou la suite du texte précédent.
CODE_INDENT = 4

ROMAN_REGEX = re.compile(
    r"^m{0,4}(?:cm|cd|d?c{0,3})(?:xc|xl|l?x{0,3})(?:ix|iv|v?i{0,3})$"
)
ROMAN_VALUES = {"i": 1, "v": 5, "x": 10, "l": 50, "c": 100, "d": 500, "m": 1000}
MAX_DIGITS = 9


@dataclass(frozen=True)
class Marker:
    """Un marqueur d'élément de liste.

    `kind` : `bullet`, `decimal`, `alpha`, `roman`, `auto` (`#.`) ou `example`
    (`(@)`). `delimiter` : `.`, `)` ou `()` pour `(a)`. `value` : le nombre, le rang
    de la lettre (a = 1) ou la valeur du chiffre romain ; 1 pour `#.` et `(@)`.
    """

    kind: str
    upper: bool = False
    delimiter: str = ""
    value: int = 1

    @property
    def ordered(self) -> bool:
        return self.kind != "bullet"

    @property
    def style(self) -> tuple[str, bool, str]:
        """Deux éléments de même style sont de la même liste ; sinon Pandoc en
        commence une autre (autre type, autre casse, autre séparateur)."""
        return (self.kind, self.upper, self.delimiter)

    @property
    def list_type(self) -> str:
        """Attribut `type` de la balise `<ol>` : 1, a, A, i ou I."""
        letter = {"alpha": "a", "roman": "i"}.get(self.kind)
        if letter is None:
            return "1"
        return letter.upper() if self.upper else letter

    @property
    def native(self) -> bool:
        """Python-Markdown comprend ce marqueur tel quel : puce ou `1.`."""
        return self.kind == "bullet" or (
            self.kind == "decimal" and self.delimiter == "."
        )


BULLET = Marker("bullet")


def roman_value(text: str) -> int | None:
    """Valeur d'un chiffre romain en minuscules, `None` s'il n'est pas valide."""
    if not text or not ROMAN_REGEX.match(text):
        return None
    total = 0
    for char, following in zip(text, text[1:] + " ", strict=True):
        value = ROMAN_VALUES[char]
        total += -value if ROMAN_VALUES.get(following, 0) > value else value
    return total


def parse_marker(
    marker: str, space: str = " ", context: Marker | None = None
) -> Marker | None:
    """Lit un marqueur d'élément ; `None` si ce n'en est pas un pour Pandoc.

    `space` : les espaces qui suivent. `context` : le marqueur de l'élément précédent
    de la même liste, qui décide des lettres ambiguës : dans une liste de lettres,
    `i.` est la lettre i ; dans une liste de chiffres romains, `v.`, `x.` ou `c.` sont
    des chiffres romains. Sans contexte, seul `i` (ou `I`) seul est un chiffre romain.
    """
    if marker in ("-", "*", "+"):
        return BULLET
    if marker.startswith("("):
        if not marker.endswith(")"):
            return None
        delimiter, body = "()", marker[1:-1]
    else:
        delimiter, body = marker[-1], marker[:-1]

    if body.startswith("@"):
        return Marker("example", delimiter="()") if delimiter == "()" else None
    if body == "#":
        return Marker("auto", delimiter=delimiter) if delimiter != "()" else None
    if body.isascii() and body.isdigit():
        if len(body) > MAX_DIGITS:
            return None
        return Marker("decimal", delimiter=delimiter, value=int(body))
    if not (body.isascii() and body.isalpha()):
        return None
    upper = body.isupper()
    if not (upper or body.islower()):
        return None
    # Une majuscule seule suivie d'un point est une initiale (« A. Dupont ») : pour
    # que ce soit une liste, Pandoc veut deux espaces au moins.
    if len(body) == 1 and upper and delimiter == "." and len(space) < 2:
        return None

    low = body.lower()
    roman = roman_value(low)
    kind = None
    if context is not None and context.upper == upper:
        if context.kind == "roman" and roman is not None:
            kind = "roman"
        elif context.kind == "alpha" and len(low) == 1:
            kind = "alpha"
    if kind is None:
        if low == "i" or (len(low) > 1 and roman is not None):
            kind = "roman"
        elif len(low) == 1:
            kind = "alpha"
        else:
            return None
    value = roman if kind == "roman" and roman is not None else ord(low[0]) - 96
    return Marker(kind, upper, delimiter, value)


class ListItemMatcher:
    """Reconnaît une ligne d'élément de liste : `match(ligne)` renvoie un `re.Match`
    (groupes `indent`, `marker`, `space`) si le marqueur en est un pour Pandoc."""

    def match(self, line: str, context: Marker | None = None) -> re.Match[str] | None:
        found = _ITEM_PATTERN.match(line)
        if found and parse_marker(found.group("marker"), found.group("space"), context):
            return found
        return None


LIST_ITEM_REGEX = ListItemMatcher()


def text_column(item: re.Match[str]) -> int:
    """Colonne du texte d'un élément de liste reconnu par `LIST_ITEM_REGEX`.

    Au-delà de 4 espaces après le marqueur, le texte est du code indenté : Pandoc
    place alors la colonne du texte juste après le marqueur.
    """
    space = len(item.group("space"))
    return item.end("marker") + (space if 0 < space <= CODE_INDENT else 1)
