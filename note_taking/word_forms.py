"""Formes réduites des mots (#372) : le singulier et le pluriel s'écrivent pareil.

Les règles de la forme réduite sont dans `core.names` (`reduce_word`), partagées avec
les noms proches des projets et des niveaux (#374) ; **sans accès à la base**. La
forme réduite sert à l'index (colonne `words` de `search_index`), aux mots de la
requête et aux noms de niveaux de `chemin:` ; la phrase exacte et le préfixe restent
tels qu'écrits.
"""

import itertools

from core.names import TOKEN_REGEX, reduce_word
from core.tables import fold

# Au-delà, un mot de plusieurs morceaux (« porte-fenêtres ») n'est surligné que tel
# que tapé ou sous sa forme réduite : le nombre de combinaisons croît vite.
MAX_COMBINATIONS = 64


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
