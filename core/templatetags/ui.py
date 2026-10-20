"""Composants d'interface partagés, à charger avec `{% load ui %}`.

Chaque balise rend un gabarit de `core/templates/core/components/`, qui porte
les classes Tailwind du composant (écrites en entier, sans les construire par
morceaux). Les icônes sont des noms de Material Symbols Rounded.
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


@register.inclusion_tag("core/components/button.html")
def button(
    label: str,
    icon: str = "",
    variant: str = "primary",
    type: str = "submit",
    icon_only: bool = False,
) -> dict:
    """Bouton de formulaire ; `variant` vaut `primary` ou `danger`."""
    return {
        "label": label,
        "icon": icon,
        "variant": variant,
        "type": type,
        "icon_only": icon_only,
    }


@register.inclusion_tag("core/components/link_button.html")
def link_button(
    href: str, label: str, icon: str = "", variant: str = "primary"
) -> dict:
    """Lien présenté comme un bouton ; `variant` vaut `primary` ou `danger`."""
    return {"href": href, "label": label, "icon": icon, "variant": variant}


@register.inclusion_tag("core/components/icon_link.html")
def icon_link(href: str, label: str, icon: str, variant: str = "default") -> dict:
    """Lien réduit à une icône ; `label` en donne le sens aux lecteurs d'écran."""
    return {"href": href, "label": label, "icon": icon, "variant": variant}


@register.inclusion_tag("core/components/tag_list.html")
def tag_list(tags) -> dict:
    """Liste de tags en pastilles ; rien n'est rendu si elle est vide."""
    return {"tags": tags}
