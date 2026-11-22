"""Formatage des dates affichées (#129), commun aux apps.

Le filtre `date_text` et la balise `{% date_time %}` de `{% load ui %}`
(core/templatetags/ui.py) s'appuient sur ce module ; le code Python (vues,
modèles, messages) l'importe directement.
"""

import datetime

from django.template.defaultfilters import date as format_date
from django.utils import timezone

# Formats d'affichage des dates (#129), selon l'usage :
# - long : la date nomme une note (titres, liens « Note du … ») ;
# - moyen : une date dans un texte ou une fiche (échéance, dates d'une image) ;
# - court : tableaux et listes.
# Le jour s'écrit `j`, en chiffres sans zéro : « 1er » le premier du mois (#383).
# N plutôt que M pour le mois abrégé : en français, M donne « Jui » pour juin et juillet.
DATE_FORMATS = {
    "long": "l j F Y",
    "moyen": "j F Y",
    "court": "D. j N Y",
}


def local(value):
    """Une date et heure dans le fuseau de l'application (TIME_ZONE)."""
    if isinstance(value, datetime.datetime) and timezone.is_aware(value):
        return timezone.localtime(value)
    return value


def date_text(value, style: str = "moyen") -> str:
    """Date en texte selon son format d'affichage (`long`, `moyen`, `court`).

    Pour un attribut ou un message ; dans une page, préférer `{% date_time %}`.
    """
    if style not in DATE_FORMATS:
        raise ValueError(f"Format de date inconnu : {style}")
    if value in (None, ""):
        return ""
    value = local(value)
    date_format = DATE_FORMATS[style]
    if value.day == 1:
        # Le 1er du mois (#383) : « jeudi 1er octobre 2026 ». Les formats écrivent
        # le jour par `j` (en chiffres, sans zéro) ; « er » échappé est du texte.
        date_format = date_format.replace("j", r"j\e\r")
    return format_date(value, date_format)


def machine_date(value) -> str:
    """Date, ou date et heure, au format de l'attribut `datetime` de `<time>`.

    Une heure se donne à la seconde : le format n'admet que 3 décimales (#259).
    """
    if isinstance(value, datetime.datetime):
        return value.isoformat(timespec="seconds")
    return value.isoformat()


def parse_date_param(value: str) -> datetime.date | None:
    """Date d'un paramètre d'adresse au format AAAA-MM-JJ, ou None si la valeur
    n'en est pas une (partagé par les vues des notes et des tâches, #190)."""
    try:
        return datetime.date.fromisoformat(value)
    except ValueError:
        return None
