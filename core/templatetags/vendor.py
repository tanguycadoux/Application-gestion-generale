"""Import maps des scripts en modules, à charger avec `{% load vendor %}`."""

import json

from django import template
from django.utils.html import format_html
from django.utils.safestring import SafeString

from core.codemirror import import_map
from core.static_files import module_imports

register = template.Library()


def _importmap(imports: dict[str, str]) -> SafeString:
    """Balise `<script type="importmap">`, à placer avant les scripts de la page.

    Les adresses viennent de nos propres fichiers : le navigateur ne contacte aucun
    autre serveur. Les `<` sont écrits en `\\u003c` pour qu'aucune valeur ne puisse
    fermer la balise.
    """
    data = json.dumps({"imports": imports}, indent=2).replace("<", "\\u003c")
    return format_html('<script type="importmap">\n{}\n</script>', SafeString(data))


@register.simple_tag
def codemirror_importmap(*entries: str) -> SafeString:
    """Import map des modules CodeMirror embarqués (#89), et de ceux que les scripts
    donnés importent par `./x.js` (#469). Une page n'a qu'une import map."""
    return _importmap(import_map()["imports"] | module_imports(*entries))


@register.simple_tag
def modules_importmap(*entries: str) -> SafeString:
    """Import map des modules que les scripts donnés importent par `./x.js` (#469), pour
    une page sans CodeMirror."""
    return _importmap(module_imports(*entries))
