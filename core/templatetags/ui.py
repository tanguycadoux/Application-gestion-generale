"""Composants d'interface partagés, à charger avec `{% load ui %}`.

Chaque balise rend un gabarit de `core/templates/core/components/`. Les classes
Tailwind sont dans le gabarit, ou ici quand elles dépendent d'une variante,
toujours écrites en entier (sans les construire par morceaux). Les icônes sont
des noms de Material Symbols Rounded.
"""

from django import template
from django.urls import reverse

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


# Classes de chaque variante de bouton, écrites en entier.
BUTTON_VARIANTS = {
    "primary": (
        "inline-flex items-center gap-2 my-[.4rem] rounded-[.8rem] p-[.6rem]"
        " font-semibold bg-primary-93 text-primary-40 hover:bg-primary-95"
    ),
    "danger": (
        "inline-flex items-center gap-2 my-[.4rem] rounded-[.8rem] p-[.6rem]"
        " font-semibold bg-alert-93 text-alert-40 hover:bg-alert-95"
    ),
    "ghost": "inline-flex items-center gap-2 rounded-2xl p-2 hover:bg-slate-200",
    "ghost-danger": "inline-flex items-center gap-2 rounded-2xl p-2 hover:bg-red-200",
}


@register.inclusion_tag("core/components/button.html")
def button(
    label: str,
    href: str = "",
    icon: str = "",
    variant: str = "primary",
    type: str = "submit",
    icon_only: bool = False,
) -> dict:
    """Bouton de l'app : lien `<a>` si `href` est fourni, sinon `<button>`.

    - `variant` : `primary`, `danger`, `ghost` (fond transparent) ou
      `ghost-danger` ;
    - `type` : type du `<button>`, ignoré pour un lien ;
    - `icon_only` : n'affiche que l'icône, le libellé passe en `aria-label`.
    """
    if variant not in BUTTON_VARIANTS:
        raise ValueError(f"Variante de bouton inconnue : {variant}")
    return {
        "label": label,
        "href": href,
        "icon": icon,
        "classes": BUTTON_VARIANTS[variant],
        "type": type,
        "icon_only": icon_only,
    }


@register.inclusion_tag("core/components/tag_list.html")
def tag_list(tags) -> dict:
    """Liste de tags en pastilles ; rien n'est rendu si elle est vide."""
    return {"tags": tags}
