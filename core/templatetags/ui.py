"""Composants d'interface partagés, à charger avec `{% load ui %}`.

Chaque balise rend un gabarit de `core/templates/core/components/`. Les classes
Tailwind sont dans le gabarit, ou ici quand elles dépendent d'une variante,
toujours écrites en entier (sans les construire par morceaux). Les icônes sont
des noms de Material Symbols Rounded.
"""

import datetime

from django import template
from django.template.defaultfilters import date as format_date
from django.urls import reverse
from django.utils import timezone
from django.utils.html import format_html, json_script

register = template.Library()


@register.inclusion_tag("core/components/nav_link.html", takes_context=True)
def nav_link(context, url_name: str, label: str, icon: str) -> dict:
    """Lien du menu, marqué actif sur la page qu'il désigne."""
    url = reverse(url_name)
    request = context.get("request")
    return {
        "url": url,
        "label": label,
        "icon": icon,
        "active": request is not None and request.path == url,
    }


# Forme commune à toutes les variantes de bouton (#145).
BUTTON_SHAPE = "inline-flex items-center gap-2 rounded-xl p-2 font-semibold"

# Classes de chaque variante de bouton, écrites en entier. Pleins : l'action
# principale, le fond s'éclaircit au survol. Ghost : les actions sur l'objet
# affiché et la navigation, sans fond sauf au survol.
BUTTON_VARIANTS = {
    "primary": BUTTON_SHAPE + " bg-blue-100 text-blue-800 hover:bg-blue-50",
    "danger": BUTTON_SHAPE + " bg-red-100 text-red-800 hover:bg-red-50",
    "ghost": BUTTON_SHAPE + " hover:bg-slate-200",
    "ghost-danger": BUTTON_SHAPE + " text-red-800 hover:bg-red-100",
}


@register.simple_tag
def button_variants_json() -> str:
    """Classes des variantes de bouton pour les scripts qui créent des boutons
    (alertes, #154), dans un `<script id="button-variants" type="application/json">`."""
    return json_script(BUTTON_VARIANTS, "button-variants")


@register.inclusion_tag("core/components/button.html")
def button(
    label: str,
    href: str = "",
    icon: str = "",
    variant: str = "primary",
    type: str = "submit",
    icon_only: bool = False,
    disabled: bool = False,
    form: str = "",
) -> dict:
    """Bouton de l'app : lien `<a>` si `href` est fourni, sinon `<button>`.

    - `variant` : `primary`, `danger`, `ghost` (fond transparent) ou
      `ghost-danger` ;
    - `type` : type du `<button>`, ignoré pour un lien ;
    - `icon_only` : n'affiche que l'icône, le libellé passe en `aria-label` ;
    - `disabled` : bouton désactivé, sans effet de survol (pas pour un lien,
      qui n'a pas d'état désactivé en HTML) ;
    - `form` : identifiant du formulaire que le bouton envoie, quand il est
      placé hors de ce formulaire (barre d'outils de l'en-tête) ; pas pour un lien.
    """
    if variant not in BUTTON_VARIANTS:
        raise ValueError(f"Variante de bouton inconnue : {variant}")
    if disabled and href:
        raise ValueError("Un lien ne peut pas être désactivé : retirer href.")
    if form and href:
        raise ValueError("Un lien n'envoie pas de formulaire : retirer href.")

    classes = BUTTON_VARIANTS[variant]
    if disabled:
        classes = " ".join(
            [c for c in classes.split() if not c.startswith("hover:")]
            + ["cursor-not-allowed", "opacity-50"]
        )
    return {
        "label": label,
        "href": href,
        "icon": icon,
        "classes": classes,
        "type": type,
        "icon_only": icon_only,
        "disabled": disabled,
        "form": form,
    }


@register.inclusion_tag("core/components/tag_list.html")
def tag_list(tags) -> dict:
    """Liste de tags en pastilles ; rien n'est rendu si elle est vide."""
    return {"tags": tags}


# Formats d'affichage des dates (#129), selon l'usage :
# - long : la date nomme une note (titres, liens « Note du … ») ;
# - moyen : une date dans un texte ou une fiche (échéance, dates d'une image) ;
# - court : tableaux et listes.
# N plutôt que M pour le mois abrégé : en français, M donne « Jui » pour juin et juillet.
DATE_FORMATS = {
    "long": "l j F Y",
    "moyen": "j F Y",
    "court": "D. j N Y",
}


def _local(value):
    """Une date et heure dans le fuseau de l'application (TIME_ZONE)."""
    if isinstance(value, datetime.datetime) and timezone.is_aware(value):
        return timezone.localtime(value)
    return value


@register.filter
def date_text(value, style: str = "moyen") -> str:
    """Date en texte selon son format d'affichage (`long`, `moyen`, `court`).

    Pour un attribut ou un message ; dans une page, préférer `{% date_time %}`.
    """
    if style not in DATE_FORMATS:
        raise ValueError(f"Format de date inconnu : {style}")
    if value in (None, ""):
        return ""
    return format_date(_local(value), DATE_FORMATS[style])


@register.simple_tag
def date_time(value, style: str = "moyen") -> str:
    """Date affichée selon son format, dans un `<time datetime="…">`."""
    if value in (None, ""):
        return ""
    value = _local(value)
    return format_html(
        '<time datetime="{}">{}</time>', value.isoformat(), date_text(value, style)
    )
