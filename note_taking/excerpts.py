"""Extraits de notes en texte : une ligne lisible, sans les marques du Markdown."""

import re

from django.utils.text import Truncator

from .qmd.parser import BLOCK_END, CODE_FENCE, METADATA_BLOCK_START

# Longueur d'un extrait, en caractères, points de suspension compris.
EXCERPT_LENGTH = 160

# Ce qui ne se lit pas dans un extrait : marque de liste, de citation ou de titre
# en début de ligne, case à cocher.
LINE_MARKER_REGEX = re.compile(r"^\s*(?:[-*+>]|\d+[.)]|#+)\s+(?:\[[ xX]\]\s+)?")
# Lien ou image : son texte seul.
LINK_REGEX = re.compile(r"!?\[(?P<text>[^\]\n]*)\]\([^)\n]*\)(?:\{[^}\n]*\})?")
# Une ligne sans mot (filet, séparation d'un tableau).
WORD_REGEX = re.compile(r"\w")


def plain_line(line: str) -> str:
    """Le texte d'une ligne, raccourci : sans marque de début, les liens et les images
    réduits à leur texte."""
    text = LINK_REGEX.sub(lambda m: m["text"], LINE_MARKER_REGEX.sub("", line))
    return Truncator(" ".join(text.split())).chars(EXCERPT_LENGTH)


def first_words(lines: list[str]) -> str:
    """La première ligne de texte de ces lignes d'une note (#376), vide s'il n'y en a
    pas : ni titre, ni bloc de métadonnées, ni ouverture d'un bloc `:::` ou de code."""
    in_metadata = False
    for line in lines:
        stripped = line.strip()
        if in_metadata:
            in_metadata = stripped != BLOCK_END
        elif stripped == METADATA_BLOCK_START:
            in_metadata = True
        elif not stripped.startswith(("#", BLOCK_END, CODE_FENCE)):
            text = plain_line(line)
            if WORD_REGEX.search(text):
                return text
    return ""
