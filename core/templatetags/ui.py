"""Composants d'interface partagés, à charger avec `{% load ui %}`.

Chaque balise rend un gabarit de `core/templates/core/components/`. Les classes
Tailwind sont dans le gabarit, ou ici quand elles dépendent d'une variante,
toujours écrites en entier (sans les construire par morceaux). Les icônes sont
des noms de Material Symbols Rounded, en SVG inline (`{% icon %}`, core/icons.py).
"""

import datetime

from django import template
from django.template.defaultfilters import date as format_date
from django.urls import reverse
from django.utils import timezone
from django.utils.html import format_html
from django.utils.safestring import SafeString

from core.icons import DEFAULT_CLASSES, UnknownIconError, icon_svg

register = template.Library()


@register.simple_tag
def icon(name: str, label: str = "", **attrs) -> SafeString:
    """Icône Material Symbols en SVG inline (#218) : `{% icon "save" %}`.

    Taille et couleur par classes (`class="size-4 text-amber-600"`, 24 px par
    défaut), décorative sauf si `label` est donné (icône seule qui porte un sens).
    """
    try:
        return icon_svg(name, attrs.get("class", DEFAULT_CLASSES), label)
    except UnknownIconError as error:
        raise template.TemplateSyntaxError(str(error)) from error


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


# Classes écrites en entier, pour que Tailwind les trouve.
INDENT_CLASSES = ["pl-0", "pl-6", "pl-12", "pl-18", "pl-24", "pl-30", "pl-36"]


@register.filter
def indent_class(depth: int) -> str:
    """Indentation d'un niveau de l'arbre des chemins, borné à la profondeur max."""
    return INDENT_CLASSES[min(depth, len(INDENT_CLASSES) - 1)]


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
    describedby: str = "",
    popovertarget: str = "",
    popovertargetaction: str = "",
) -> dict:
    """Bouton de l'app : lien `<a>` si `href` est fourni, sinon `<button>`.

    - `variant` : `primary`, `danger`, `ghost` (fond transparent) ou
      `ghost-danger` ;
    - `type` : type du `<button>`, ignoré pour un lien ;
    - `icon_only` : n'affiche que l'icône, le libellé passe en `aria-label` ;
    - `disabled` : bouton désactivé, sans effet de survol (pas pour un lien,
      qui n'a pas d'état désactivé en HTML) ;
    - `form` : identifiant du formulaire que le bouton envoie, quand il est
      placé hors de ce formulaire (barre d'outils de l'en-tête) ; pas pour un lien ;
    - `describedby` : identifiant du texte qui décrit le bouton (`aria-describedby`),
      par exemple la raison pour laquelle il est désactivé ;
    - `popovertarget`, `popovertargetaction` : popover native que le bouton
      ouvre, ou ferme avec `"hide"` ; pas pour un lien.
    """
    if variant not in BUTTON_VARIANTS:
        raise ValueError(f"Variante de bouton inconnue : {variant}")
    if disabled and href:
        raise ValueError("Un lien ne peut pas être désactivé : retirer href.")
    if form and href:
        raise ValueError("Un lien n'envoie pas de formulaire : retirer href.")
    if popovertarget and href:
        raise ValueError("Un lien n'ouvre pas de popover : retirer href.")

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
        "describedby": describedby,
        "popovertarget": popovertarget,
        "popovertargetaction": popovertargetaction,
    }


@register.inclusion_tag("core/components/confirm_button.html", takes_context=True)
def confirm_button(
    context,
    label: str,
    id: str,
    message: str,
    action: str,
    icon: str = "",
    variant: str = "ghost-danger",
    icon_only: bool = False,
    confirm_label: str = "Supprimer",
    confirm_icon: str = "delete",
    confirm_variant: str = "danger",
    disabled: bool = False,
    describedby: str = "",
) -> dict:
    """Bouton qui demande confirmation avant d'envoyer un POST (#292).

    Une popover HTML native, sans JavaScript : le bouton l'ouvre, le navigateur
    la ferme (Échap, clic à côté, « Annuler ») et la place sous le bouton
    (`.confirm-popover`). Elle contient le `message` et le formulaire POST vers
    `action`, avec « Annuler » puis l'action.

    - `label`, `icon`, `variant`, `icon_only` : le bouton de la page (comme `button`) ;
    - `id` : identifiant de la popover, unique dans la page ;
    - `confirm_label`, `confirm_icon`, `confirm_variant` : l'action de la popover
      (« Supprimer » en `danger` par défaut, « Rétablir » en `primary`) ;
    - `disabled`, `describedby` : bouton désactivé relié à la raison, sans popover.
    """
    return {
        "label": label,
        "id": id,
        "message": message,
        "action": action,
        "icon": icon,
        "variant": variant,
        "icon_only": icon_only,
        "confirm_label": confirm_label,
        "confirm_icon": confirm_icon,
        "confirm_variant": confirm_variant,
        "disabled": disabled,
        "describedby": describedby,
        "csrf_token": context.get("csrf_token", ""),
    }


# Alertes : une variante par niveau de message. Gris : `slate`, la famille des gris
# de l'app.
ALERT_BASE = "flex items-start gap-2 rounded-md border p-3 text-sm"
ALERT_VARIANTS = {
    "primary": "border-blue-200 bg-blue-50 text-blue-900",
    "secondary": "border-slate-200 bg-slate-50 text-slate-900",
    "danger": "border-red-200 bg-red-50 text-red-900",
    "warning": "border-amber-200 bg-amber-50 text-amber-900",
    "success": "border-green-200 bg-green-50 text-green-900",
}
ALERT_ICONS = {
    "primary": "info",
    "secondary": "info",
    "danger": "error",
    "warning": "warning",
    "success": "check_circle",
}

# Niveaux de django.contrib.messages, en variantes d'alerte.
MESSAGE_VARIANTS = {
    "debug": "secondary",
    "info": "primary",
    "success": "success",
    "warning": "warning",
    "error": "danger",
}

TOAST_CLASSES = "pointer-events-auto shadow-lg"
# Succès et informations disparaissent d'eux-mêmes (core/static/core/toasts.js) ;
# les avertissements et les erreurs restent.
AUTOHIDE_VARIANTS = {"primary", "secondary", "success"}


def toast_context(message, level_tag: str) -> dict:
    variant = MESSAGE_VARIANTS.get(level_tag, "primary")
    return {
        "message": message,
        "icon": ALERT_ICONS[variant],
        "classes": f"{ALERT_BASE} {ALERT_VARIANTS[variant]} {TOAST_CLASSES}",
        # Une erreur interrompt les lecteurs d'écran ; les autres messages attendent.
        "role": "alert" if variant == "danger" else "status",
        "autohide": variant in AUTOHIDE_VARIANTS,
    }


@register.inclusion_tag("core/components/toast.html")
def message_toast(message) -> dict:
    """Un message de django.contrib.messages, en notification (toast) : HTML rendu
    par le serveur (#293), visible sans JavaScript, où il reste alors affiché.
    `toasts.js` ajoute la fermeture (bouton, Échap) et la disparition des succès."""
    return toast_context(message, message.level_tag)


@register.inclusion_tag("core/components/toast.html")
def toast_template(level_tag: str) -> dict:
    """Modèle de toast sans texte, cloné par `Toast.show` pour les messages créés
    par un script (échec réseau, image importée)."""
    return toast_context("", level_tag)


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
    # Une heure se donne à la seconde : le format n'admet que 3 décimales (#259).
    machine = (
        value.isoformat(timespec="seconds")
        if isinstance(value, datetime.datetime)
        else value.isoformat()
    )
    return format_html(
        '<time datetime="{}">{}</time>', machine, date_text(value, style)
    )


# Point de couleur de chaque famille de projet (core.models.PROJECT_COLORS),
# écrit en entier pour que Tailwind trouve les classes.
PROJECT_DOT_CLASSES = {
    "orange": "bg-orange-500",
    "yellow": "bg-yellow-500",
    "lime": "bg-lime-500",
    "emerald": "bg-emerald-500",
    "teal": "bg-teal-500",
    "cyan": "bg-cyan-500",
    "sky": "bg-sky-500",
    "indigo": "bg-indigo-500",
    "violet": "bg-violet-500",
    "purple": "bg-purple-500",
    "fuchsia": "bg-fuchsia-500",
    "pink": "bg-pink-500",
    "rose": "bg-rose-500",
}


@register.filter
def project_dot_class(project) -> str:
    """Classe du point de couleur d'un projet, pour un affichage compact."""
    return PROJECT_DOT_CLASSES.get(project.color, "") if project else ""


@register.inclusion_tag("core/components/project_badge.html")
def project_badge(project) -> dict:
    """Pastille d'un projet : un point de sa couleur devant son nom ; rien sans projet."""
    return {
        "project": project,
        "dot_class": PROJECT_DOT_CLASSES.get(project.color, "") if project else "",
    }


@register.simple_tag
def calendar_cell_classes(day, inactive: bool = False, clickable: bool = True) -> str:
    """Classes d'une case du calendrier mensuel (#88, #167), communes aux apps.

    `inactive` : jour sans action possible (pointillés) ; `clickable` : la case
    entière est un lien (fond au survol).
    """
    classes = [
        "group relative flex h-full min-h-24 min-w-0 flex-col gap-1 rounded-lg border p-1.5"
    ]
    if inactive:
        classes.append("cursor-not-allowed border-dashed border-slate-300")
        classes.append("bg-slate-100" if day.is_weekend else "bg-transparent")
    else:
        classes.append("border-slate-200")
        if clickable:
            classes.append("hover:bg-blue-50")
        classes.append("bg-slate-100" if day.is_weekend else "bg-white")
    if not day.in_month:
        classes.append("opacity-40")
    if day.is_today:
        classes.append("ring-2 ring-blue-500")
    return " ".join(classes)


@register.simple_tag
def calendar_number_classes(day, inactive: bool = False) -> str:
    """Classes du numéro d'un jour dans sa case."""
    if day.is_today:
        return "text-sm font-bold text-blue-800"
    if inactive:
        return "text-sm text-slate-300"
    if day.is_weekend:
        return "text-sm text-slate-400"
    return "text-sm text-slate-600"
