"""Typographie française de l'interface (#383).

`nbsp_punct` remplace l'espace avant `;`, `:`, `!`, `?` et `»`, et après `«`, par
une espace insécable (U+00A0) : la ligne ne se coupe plus entre le mot et sa
ponctuation. Plutôt que de corriger chaque chaîne du code, le filtre s'applique
au rendu : messages en toast, composants communs (bouton, confirmation), textes
des gabarits (`{% filter nbsp_punct %}…{% endfilter %}`). Jamais au contenu des
notes ni aux valeurs des champs.

Seules les espaces déjà écrites changent : « 10:30 » ou `chemin:` restent tels
quels. Plusieurs espaces deviennent une seule ; une espace insécable (ou fine)
déjà là est gardée.
"""

import re

from django.utils.html import conditional_escape
from django.utils.safestring import SafeData, mark_safe

NBSP = "\u00a0"

# Espaces ordinaires, éventuellement plusieurs ou mêlées d'insécables.
_BEFORE = re.compile(r"[ \u00a0\u202f]*[ ][ \u00a0\u202f]*(?=[;:!?»])")
_AFTER = re.compile(r"(?<=«)[ \u00a0\u202f]*[ ][ \u00a0\u202f]*")

# Dans du HTML : les balises, et les éléments dont le texte est du code ou une
# valeur (laissés intacts).
_HTML_PARTS = re.compile(
    r"(<(code|kbd|pre|samp|textarea|script|style)\b.*?</\2\s*>|<[^>]*>)",
    re.IGNORECASE | re.DOTALL,
)


def _replace(text: str) -> str:
    text = _BEFORE.sub(NBSP, text)
    return _AFTER.sub(NBSP, text)


def nbsp_punct(value, autoescape: bool = True) -> str:
    """Le texte avec les espaces insécables, échappé (sauf `autoescape` faux).

    Un texte déjà sûr (HTML) n'est modifié qu'entre les balises.
    """
    text = str(value)
    if isinstance(text, SafeData):
        parts = _HTML_PARTS.split(text)
        # split rend [texte, balise, nom ou None, texte, …] : un texte sur trois.
        return mark_safe(
            "".join(
                _replace(part) if index % 3 == 0 else (part or "")
                for index, part in enumerate(parts)
                if index % 3 != 2
            )
        )
    if autoescape:
        return mark_safe(_replace(conditional_escape(text)))
    return _replace(text)
