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
