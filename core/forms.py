from django.forms.renderers import DjangoTemplates


class GridFormRenderer(DjangoTemplates):
    """Rend `{{ form }}` en grille : libellé à gauche, champ à droite (#132).

    Le `<form>` porte la grille ; chaque champ y occupe deux cellules.
    """

    form_template_name = "core/forms/grid.html"
