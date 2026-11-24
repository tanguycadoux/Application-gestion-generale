"""Composants d'interface partagés, à charger avec `{% load ui %}`.

Chaque balise rend un gabarit de `core/templates/core/components/`. Les classes
Tailwind sont dans le gabarit, ou ici quand elles dépendent d'une variante,
toujours écrites en entier (sans les construire par morceaux). Les icônes sont
des noms de Material Symbols Rounded, en SVG inline (`{% icon %}`, core/icons.py).

La logique qui n'est pas un composant vit dans des modules de `core`, dont les
fonctions sont enregistrées ici telles quelles : formatage des dates
(core/dates.py), couleurs des projets (core/project_colors.py), classes des cases
du calendrier (core/calendar_cells.py), espaces insécables (core/typography.py). Le code Python les importe depuis ces
modules, pas depuis cette bibliothèque de balises.
"""

from django import template
from django.urls import reverse
from django.utils.html import format_html
from django.utils.safestring import SafeString

from core.calendar_cells import calendar_cell_classes, calendar_number_classes
from core.dates import date_text, local, machine_date
from core.icons import DEFAULT_CLASSES, UnknownIconError, icon_svg
from core.project_colors import project_dot_class
from core.tables import header_context, summary_context
from core.typography import nbsp_punct

register = template.Library()

register.filter("date_text", date_text)
register.filter("project_dot_class", project_dot_class)
# Espaces insécables avant « ; : ! ? » et dans les guillemets (#383).
register.filter("nbsp_punct", nbsp_punct, is_safe=True, needs_autoescape=True)
register.simple_tag(calendar_cell_classes)
register.simple_tag(calendar_number_classes)


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
    keyshortcuts: str = "",
    name: str = "",
    value: str = "",
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
      ouvre, ou ferme avec `"hide"` ; pas pour un lien ;
    - `keyshortcuts` : raccourci clavier que gère la page, annoncé aux technologies
      d'assistance (`aria-keyshortcuts`, par exemple `"ArrowLeft"`, #276) ;
    - `name`, `value` : nom et valeur envoyés avec le formulaire quand ce bouton
      l'envoie, pour distinguer deux boutons d'un même formulaire (#389) ; pas
      pour un lien.
    """
    if variant not in BUTTON_VARIANTS:
        raise ValueError(f"Variante de bouton inconnue : {variant}")
    if disabled and href:
        raise ValueError("Un lien ne peut pas être désactivé : retirer href.")
    if form and href:
        raise ValueError("Un lien n'envoie pas de formulaire : retirer href.")
    if popovertarget and href:
        raise ValueError("Un lien n'ouvre pas de popover : retirer href.")
    if name and href:
        raise ValueError("Un lien n'envoie pas de valeur : retirer href.")

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
        "keyshortcuts": keyshortcuts,
        "name": name,
        "value": value,
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


@register.simple_tag
def kbd(keys: str) -> SafeString:
    """Un raccourci clavier (`←`, `Ctrl+K`) en `<kbd>` discret (#276).

    En police à chasse fixe (`font-mono`), comme l'indice de la barre de recherche
    (#355).
    """
    return format_html(
        '<kbd class="rounded border border-slate-300 bg-white px-1 font-mono text-xs'
        ' text-slate-600">{}</kbd>',
        keys,
    )


@register.inclusion_tag("core/components/tag_list.html")
def tag_list(tags) -> dict:
    """Liste de tags en pastilles ; rien n'est rendu si elle est vide."""
    return {"tags": tags}


@register.simple_tag
def date_time(value, style: str = "moyen") -> str:
    """Date affichée selon son format, dans un `<time datetime="…">`."""
    if value in (None, ""):
        return ""
    value = local(value)
    return format_html(
        '<time datetime="{}">{}</time>', machine_date(value), date_text(value, style)
    )


@register.inclusion_tag("core/components/project_badge.html")
def project_badge(project, link: bool = False) -> dict:
    """Pastille d'un projet : un point de sa couleur devant son nom ; rien sans projet.

    `link` : le nom mène à la fiche du projet (#205) ; pas dans un lien ou un label.
    """
    return {
        "link": link,
        "project": project,
        "dot_class": project_dot_class(project),
    }


@register.inclusion_tag("core/components/column_header.html", takes_context=True)
def column_header(context, label: str, column: str, classes: str = "") -> dict:
    """En-tête de colonne d'un tableau trié et filtré côté serveur (#178).

    `{% column_header "Date" "date" classes="p-2" %}` : avec `sorting` et `sort`
    dans le contexte de la page, un lien qui trie par la colonne (ou inverse le
    tri) ; avec `filters` et `active_filters`, un entonnoir qui ouvre les filtres
    de la colonne. Voir `core/tables.py`.
    """
    header = header_context(
        context["request"],
        label,
        column,
        context.get("sorting"),
        context.get("sort"),
        context.get("filters"),
        context.get("active_filters"),
    )
    return {**header, "classes": classes}


@register.inclusion_tag("core/components/filter_summary.html", takes_context=True)
def filter_summary(context) -> dict:
    """Les filtres actifs au-dessus d'un tableau, chacun retiré d'un clic."""
    return summary_context(
        context["request"], context.get("filters"), context.get("active_filters")
    )


PATH_TREE_MODES = ("link", "checkbox")


@register.inclusion_tag("core/components/path_tree.html", takes_context=True)
def path_tree(
    context,
    nodes,
    mode: str = "link",
    param: str = "path",
    label: str = "Chemins",
    project_param: str = "",
    count_noun: str = "",
    faceted: bool = False,
) -> dict:
    """Arbre des chemins (#302) : `{% path_tree nodes mode="checkbox" param="path" %}`.

    `nodes` vient de `core.path_tree.path_tree`. Les niveaux se replient par un
    `<details>` natif, ouvert d'office quand un descendant est choisi : tout marche
    sans JavaScript.

    - `mode="link"` : chaque niveau est un lien vers la page courante avec
      `?param=<clé>`, le reste de la requête gardé et `page` retiré. Le niveau choisi
      est marqué (`aria-current`) et son lien retire le filtre ;
    - `mode="checkbox"` : une case `name=param`, à placer dans un formulaire ;
    - `label` : nom accessible de l'arbre ;
    - `project_param` : en mode case, fait de chaque projet une case
      `name=project_param` (valeur : son identifiant), à côté de ses niveaux ;
    - `count_noun` : ce que compte le compteur, au singulier (« passage ») ; le
      compteur reste « (12) » à l'écran, et se lit « 12 passages » au survol et
      par un lecteur d'écran (#362). Sans lui, le nombre seul.
    - `faceted` : les compteurs sont ceux d'un résultat (#380) ; un nœud à 0 reste
      affiché, atténué (`data-zero`), au lieu de n'avoir aucun compteur.

    Le compteur et la marque `chemin:` d'un nœud sont dans `#<clé>-facet`
    (`path_tree_facet.html`) : une réponse htmx peut les remplacer seuls
    (`hx-swap-oob`), sans toucher aux cases ni aux niveaux ouverts.

    Sans `project_param`, un projet n'est ni un lien ni une case.
    """
    if mode not in PATH_TREE_MODES:
        raise ValueError(f"Mode d'arbre des chemins inconnu : {mode}")
    if mode == "link":
        request = context["request"]
        query = request.GET.copy()
        query.pop(param, None)
        query.pop("page", None)
        for node in nodes:
            if node.selectable:
                shown = query.copy()
                if not node.selected:
                    shown[param] = str(node.pk)
                node.href = (
                    f"{request.path}?{shown.urlencode()}" if shown else request.path
                )
    return {
        "roots": [node for node in nodes if node.depth == 0],
        "mode": mode,
        "param": param,
        "label": label,
        "project_param": project_param if mode == "checkbox" else "",
        "count_noun": count_noun,
        "faceted": faceted,
    }
