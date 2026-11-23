"""Noms proches (#372, #374) : comparer deux noms comme la recherche les compare.

Le singulier et le pluriel s'écrivent pareil sous leur **forme réduite** : règles
simples, écrites à la main, sans racinisation complète (qui confond trop de mots).
Sur un mot déjà sans casse ni accents (`fold`), de lettres seules et d'au moins
`MIN_LENGTH` lettres :

- `-eaux` perd son x (« tableaux » → « tableau ») ;
- `-aux` devient `-al` (« journaux » → « journal ») ;
- un `s` ou un `x` final est retiré (« thermiques » → « thermique »).

Un mot plus court (« bus », « os », « mots », « mais », « mois ») ou qui contient un
chiffre reste tel quel. La recherche s'en sert pour son index (`note_taking.word_forms`) ;
`similar_key` pour repérer les projets et les niveaux qui sont probablement le même
(#374). Pas de distance d'édition : trop de faux positifs entre noms courts.
"""

import re

from .tables import fold

# Un mot : une suite de lettres et de chiffres, comme le découpe le tokenizer
# `unicode61` de FTS5 (le tiret bas et la ponctuation séparent).
TOKEN_REGEX = re.compile(r"[^\W_]+")
# Les mots de moins de 5 lettres restent tels quels : « mais » n'est pas « mai ».
MIN_LENGTH = 5


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


def similar_key(name: str) -> str:
    """Ce qui reste d'un nom sans casse, accents, ponctuation ni pluriel simple :
    deux noms de même clé sont probablement le même (« Reunion de chantier » et
    « Réunion de chantier », « Calculs thermiques » et « Calcul thermique »)."""
    return " ".join(reduce_word(word) for word in TOKEN_REGEX.findall(fold(name)))
