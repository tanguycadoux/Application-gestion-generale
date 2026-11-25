from django import template
from django.utils.html import format_html_join
from django.utils.safestring import SafeString

from core.icons import icon_svg

from ..rendering import CALLOUT_DEFAULT_TITLES, CALLOUT_ICONS

register = template.Library()


@register.simple_tag
def callout_templates() -> SafeString:
    """Un `<template>` par type de callout, son icône dans sa couleur : le menu
    « Insérer » de l'éditeur les clone (`block_templates.js`, #420)."""
    return format_html_join(
        "\n",
        '<template data-callout="{}" data-label="{}">'
        '<span class="callout-{}">{}</span></template>',
        (
            (kind, CALLOUT_DEFAULT_TITLES[kind], kind, icon_svg(icon, "callout-icon"))
            for kind, icon in CALLOUT_ICONS.items()
        ),
    )
