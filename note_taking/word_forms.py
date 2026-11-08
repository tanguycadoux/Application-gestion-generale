"""Formes réduites des mots (#372) : le singulier et le pluriel s'écrivent pareil.

Règles simples, écrites à la main, sans racinisation complète (qui confond trop de
mots) ; **sans accès à la base**. Sur un mot déjà sans casse ni accents (`fold`), de
lettres seules et d'au moins `MIN_LENGTH` lettres :

- `-eaux` perd son x (« tableaux » → « tableau ») ;
- `-aux` devient `-al` (« journaux » → « journal ») ;
- un `s` ou un `x` final est retiré (« thermiques » → « thermique »).

Un mot plus court (« bus », « os », « mots », « mais », « mois ») ou qui contient un
chiffre reste tel quel. La forme réduite sert à l'index (colonne `words` de
`search_index`), aux mots de la requête et aux noms de niveaux de `chemin:` ; la phrase
exacte et le préfixe restent tels qu'écrits.
"""

import itertools
import re

from core.tables import fold

# Un mot pour l'index : une suite de lettres et de chiffres, comme le découpe le
# tokenizer `unicode61` de FTS5 (le tiret bas et la ponctuation séparent).
TOKEN_REGEX = re.compile(r"[^\W_]+")
# Les mots de moins de 5 lettres restent tels quels : « mais » n'est pas « mai ».
MIN_LENGTH = 5
# Au-delà, un mot de plusieurs morceaux (« porte-fenêtres ») n'est surligné que tel
# que tapé ou sous sa forme réduite : le nombre de combinaisons croît vite.
MAX_COMBINATIONS = 64


def reduce_word(word: str) -> str:
    """Forme réduite d'un mot sans casse ni accents."""
    if len(word) < MIN_LENGTH or not word.isalpha():
        return word
    if word.endswith("eaux"):
        return word[:-1]
    if word.endswith("aux"):
        return word[:-3] + "al"
    if word.endswith(("s", "x")):
        return word[:-1]
    return word


def reduce_text(text: str) -> str:
    """Le texte sans casse ni accents, chaque mot à sa forme réduite ; espaces et
    ponctuation sont gardés."""
    return TOKEN_REGEX.sub(lambda match: reduce_word(match.group()), fold(text))


def word_forms(reduced: str) -> list[str]:
    """Les mots (sans casse ni accents) dont la forme réduite est `reduced`."""
    candidates = [reduced, reduced + "s", reduced + "x"]
    if reduced.endswith("al"):
        candidates.append(reduced[:-2] + "aux")
    return [word for word in candidates if reduce_word(word) == reduced]


def written_forms(reduced: str) -> list[str]:
    """Les écritures possibles d'un texte réduit (`reduce_text`), mots séparés par une
    espace : « calcul » donne « calcul », « calculs » et « calculx ».

    Elles servent au surlignage, qui cherche le mot tel qu'il est écrit dans la note.
    Un texte de plusieurs mots donne chaque combinaison, jusqu'à `MAX_COMBINATIONS` ;
    au-delà, le texte réduit seul (les extraits cherchent aussi le mot tel que tapé).
    """
    tokens = TOKEN_REGEX.findall(reduced)
    choices = [word_forms(token) or [token] for token in tokens]
    count = 1
    for choice in choices:
        count *= len(choice)
    if not tokens or count > MAX_COMBINATIONS:
        return [" ".join(tokens)] if tokens else []
    return [" ".join(words) for words in itertools.product(*choices)]
