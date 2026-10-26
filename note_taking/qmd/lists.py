"""Imbrication des listes selon la règle de Pandoc, celle de Quarto (#229).

Un élément est imbriqué si son marqueur commence au moins à la colonne du texte
de l'élément parent : 2 espaces après « - », 3 après « 1. ». Le rendu des notes
et les sous-tâches issues des notes (#238) suivent cette même règle.
"""

import re

# Élément de liste : indentation, puce ou numéro, espaces avant le texte.
LIST_ITEM_REGEX = re.compile(r"^(?P<indent> *)(?P<marker>[-*+]|\d+[.)])(?P<space> +|$)")
# À 4 espaces au-delà du texte du parent, un marqueur n'ouvre plus d'élément :
# la ligne est du code, ou la suite du texte précédent.
CODE_INDENT = 4


def text_column(item: re.Match[str]) -> int:
    """Colonne du texte d'un élément de liste reconnu par `LIST_ITEM_REGEX`.

    Au-delà de 4 espaces après le marqueur, le texte est du code indenté : Pandoc
    place alors la colonne du texte juste après le marqueur.
    """
    space = len(item.group("space"))
    return item.end("marker") + (space if 0 < space <= CODE_INDENT else 1)
