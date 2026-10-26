from django import forms
from django.forms.renderers import DjangoTemplates

from .models import Project, Section
from .sections import join_path, levels, path_labels, path_suggestions, split_path


class SectionChoiceField(forms.ModelChoiceField):
    """Choix d'une section : « Projet › Réunion › Préparation ».

    Les chemins se lisent dans un seul dictionnaire, chargé à la première étiquette :
    pas une requête par option.
    """

    def label_from_instance(self, obj):
        if not hasattr(self, "_labels"):
            self._labels = path_labels()
        return self._labels[obj.pk]


class SectionPathInput(forms.TextInput):
    """Champ de texte pour un chemin, avec les chemins existants en autocomplétion
    par une liste native (`<datalist>`), sans JavaScript."""

    template_name = "core/forms/widgets/section_path.html"

    def get_context(self, name, value, attrs):
        context = super().get_context(name, value, attrs)
        widget = context["widget"]
        widget["datalist_id"] = f"{widget['attrs'].get('id', name)}-chemins"
        widget["attrs"]["list"] = widget["datalist_id"]
        widget["suggestions"] = path_suggestions()
        return context


class SectionPathField(forms.CharField):
    """Le chemin d'une section saisi en texte : « / » sépare les niveaux, « // » est
    un « / » littéral. La valeur nettoyée est la liste des niveaux ; un chemin
    inconnu est créé à l'enregistrement, par le formulaire (`section_for`)."""

    widget = SectionPathInput

    def __init__(self, **kwargs):
        kwargs.setdefault("label", "Chemin")
        kwargs.setdefault("required", False)
        kwargs.setdefault(
            "help_text",
            "Niveaux séparés par « / » (« // » pour une barre oblique). "
            "Un chemin inconnu est créé sous le projet.",
        )
        super().__init__(**kwargs)

    def to_python(self, value):
        found = split_path(super().to_python(value))
        longest = Section._meta.get_field("name").max_length
        if any(len(level) > longest for level in found):
            raise forms.ValidationError(
                f"Un niveau ne dépasse pas {longest} caractères."
            )
        return found


def section_path_text(section) -> str:
    """Le texte à saisir pour retrouver cette section (vide sans section)."""
    return join_path(levels(section)) if section else ""


class GridFormRenderer(DjangoTemplates):
    """Rend `{{ form }}` en grille : libellé à gauche, champ à droite (#132).

    Le `<form>` porte la grille ; chaque champ y occupe deux cellules.
    """

    form_template_name = "core/forms/grid.html"


class ProjectForm(forms.ModelForm):
    """Création d'un projet : nom, couleur, description."""

    class Meta:
        model = Project
        fields = ["name", "color", "description"]


class ProjectEditForm(forms.ModelForm):
    """Modification d'un projet ; le nom change par le renommage (#170)."""

    class Meta:
        model = Project
        fields = ["color", "description"]
