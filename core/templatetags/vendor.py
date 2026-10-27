"""Bibliothèques front embarquées, à charger avec `{% load vendor %}`."""

import json

from django import template
from django.utils.html import format_html
from django.utils.safestring import SafeString

from core.codemirror import import_map

register = template.Library()


@register.simple_tag
def codemirror_importmap() -> SafeString:
    """Import map des modules CodeMirror embarqués (#89), à placer avant le script.

    Les adresses viennent de nos propres fichiers : le navigateur ne contacte aucun
    autre serveur. Les `<` sont écrits en `\\u003c` pour qu'aucune valeur ne puisse
    fermer la balise.
    """
    data = json.dumps(import_map(), indent=2).replace("<", "\\u003c")
    return format_html('<script type="importmap">\n{}\n</script>', SafeString(data))
