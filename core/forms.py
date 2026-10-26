from django import forms
from django.forms.renderers import DjangoTemplates

from .models import Project, Section
from .sections import LABEL_SEPARATOR


class SectionChoiceField(forms.ModelChoiceField):
    """Choix d'une section : « Projet › Réunion › Préparation ».

    Les chemins se lisent dans un seul dictionnaire, chargé à la première étiquette :
    pas une requête par option.
    """

    def label_from_instance(self, obj):
        if not hasattr(self, "_sections"):
            self._sections = {
                section.pk: section
                for section in Section.objects.select_related("project")
            }
        section = self._sections[obj.pk]
        chain = [section]
        while chain[0].parent_id:
            chain.insert(0, self._sections[chain[0].parent_id])
        names = [section.project.name] + [level.name for level in chain]
        return LABEL_SEPARATOR.join(names)


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
