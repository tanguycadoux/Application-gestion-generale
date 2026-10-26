# Icônes Material Symbols

Icônes affichées par `{% icon "nom" %}` (`core/templatetags/ui.py`, `core/icons.py`), recopiées dans les pages en SVG inline (#218) : aucune police chargée depuis Internet.

- Source : dépôt officiel `google/material-design-icons`, dossier `symbols/web/` (style Rounded, 24 px, non rempli, graisse 400), téléchargées par `python manage.py add_icon <nom>…`. Les noms sont ceux de <https://fonts.google.com/icons>.
- Licence : Apache 2.0, dont le texte est dans `LICENSE`. Elle s'applique à ces fichiers SVG et à l'icône d'onglet `core/static/core/favicon.svg` (« edit_note », recolorée).

Pour ajouter une icône : `python manage.py add_icon <nom>`, puis l'utiliser dans un gabarit avec `{% icon "<nom>" %}` ou le paramètre `icon=` des composants. Une icône qui n'est plus utilisée peut être supprimée de ce dossier (`core/tests/test_svg_icons.py` vérifie que chaque icône utilisée est présente).
