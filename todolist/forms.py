from collections.abc import Mapping

from django import forms
from django.forms import modelformset_factory
from django.urls import reverse

from core.forms import SectionPathField, section_path_text
from core.sections import section_for

from .models import Todo
from .parent_choices import ParentContext, parent_choices


class ParentSelect(forms.Select):
    """Choix de la tâche parente (#390) : options groupées, libellé complet d'une
    option coupée en infobulle, case des tâches terminées, rechargé par htmx.

    Les options se calculent à l'affichage seulement, d'après `parent_data` (les
    valeurs saisies) : un formulaire envoyé et valide n'en a pas besoin.
    """

    template_name = "todolist/widgets/parent_select.html"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.parent_data: Mapping = {}
        self.todo: Todo | None = None
        self.titles: dict[str, str] = {}

    def create_option(
        self, name, value, label, selected, index, subindex=None, attrs=None
    ):
        option = super().create_option(
            name, value, label, selected, index, subindex, attrs
        )
        title = self.titles.get(str(value))
        if title:
            option["attrs"]["title"] = title
        return option

    def get_context(self, name, value, attrs):
        result = parent_choices(ParentContext.from_data(self.parent_data, self.todo))
        self.choices, self.titles = result.choices, result.titles
        context = super().get_context(name, value, attrs)
        context["widget"]["show_done"] = self.parent_data.get("parent_show_done") == "1"
        url = reverse("todolist:parent_choices")
        context["widget"]["choices_url"] = (
            f"{url}?todo={self.todo.pk}" if self.todo else url
        )
        return context


class SectionPathForm(forms.ModelForm):
    """Formulaire d'une tâche dont le chemin se saisit en texte (#298), sous le
    projet choisi : un chemin inconnu est créé à l'enregistrement, pas avant."""

    section_path = SectionPathField()

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance.pk:
            self.initial["section_path"] = section_path_text(self.instance.section)

    def save(self, commit=True):
        todo = super().save(commit=False)
        todo.section = section_for(
            self.cleaned_data["project"], self.cleaned_data["section_path"]
        )
        if commit:
            todo.save()
            self.save_m2m()
        return todo


class TodoForm(SectionPathForm):
    class Meta:
        model = Todo
        fields = [
            "title",
            "description",
            "progress",
            "done",
            "priority",
            "due_date",
            "project",
            "section_path",
            "tags",
            "parent",
        ]
        widgets = {
            "due_date": forms.DateInput(format=r"%Y-%m-%d", attrs={"type": "date"}),
            "progress": forms.NumberInput(attrs={"min": 0, "max": 100}),
            "parent": ParentSelect,
        }

    def __init__(self, *args, parent_data=None, **kwargs):
        """`parent_data` : projet, chemin, parent et case des terminées tels que
        saisis, quand htmx recharge le choix du parent (#390)."""
        super().__init__(*args, **kwargs)
        self.set_up_parent(parent_data)
        self.fields["due_date"].input_formats = [r"%Y-%m-%d"]
        if not (self.instance.pk and self.instance.children.exists()):
            # Sans sous-tâche, une tâche est terminée à 100 % d'avancement.
            del self.fields["done"]
        else:
            self.fields["progress"].disabled = True
            self.fields[
                "progress"
            ].help_text = (
                "Calculé à partir des sous-tâches : la moyenne de leur avancement."
            )

    def set_up_parent(self, parent_data):
        """Le parent se choisit parmi les tâches les plus proches de ce qui est
        saisi (#390). Seul l'affichage est trié : toute tâche reste acceptée, sauf
        une boucle (`Todo.clean`)."""
        widget = self.fields["parent"].widget
        widget.todo = self.instance if self.instance.pk else None
        if self.is_bound:
            widget.parent_data = self.data
        elif parent_data is not None:
            widget.parent_data = parent_data
            self.initial["parent"] = parent_data.get("parent")
        else:
            widget.parent_data = self.initial


class NoteReviewForm(SectionPathForm):
    """Ligne du bilan d'une note (#239) : ce qui se règle juste après la création
    d'une tâche, l'échéance surtout."""

    class Meta:
        model = Todo
        fields = ["due_date", "priority", "project", "section_path"]
        widgets = {
            "due_date": forms.DateInput(format=r"%Y-%m-%d", attrs={"type": "date"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["due_date"].input_formats = [r"%Y-%m-%d"]


NoteReviewFormSet = modelformset_factory(Todo, form=NoteReviewForm, extra=0)


class GoneLineForm(forms.ModelForm):
    """Ligne du bilan d'une tâche dont la ligne a disparu de la note (#240) : la
    garder, l'écarter, ou la remplacer par la tâche d'une nouvelle ligne."""

    ACTIONS = [
        ("keep", "La garder"),
        ("dismiss", "L'écarter"),
        ("replace", "La remplacer par"),
    ]

    action = forms.ChoiceField(label="Que faire", choices=ACTIONS, initial="keep")
    replacement = forms.ModelChoiceField(
        label="Nouvelle ligne",
        queryset=Todo.objects.none(),
        required=False,
        empty_label="—",
    )

    class Meta:
        model = Todo
        fields: list[str] = []

    def __init__(self, *args, replacements=None, **kwargs):
        super().__init__(*args, **kwargs)
        if replacements is not None:
            self.fields["replacement"].queryset = replacements
        # Le titre seul est ambigu : le chemin dit où est la ligne dans la note.
        self.fields["replacement"].label_from_instance = lambda todo: " › ".join(
            part for part in (todo.note_path, todo.note_part_text) if part
        )

    def clean(self):
        cleaned_data = super().clean()
        if cleaned_data.get("action") == "replace" and not cleaned_data.get(
            "replacement"
        ):
            self.add_error("replacement", "Choisir la nouvelle ligne qui la remplace.")
        return cleaned_data


class BaseGoneLineFormSet(forms.BaseModelFormSet):
    def clean(self):
        super().clean()
        chosen = [
            form.cleaned_data["replacement"]
            for form in self.forms
            if form.cleaned_data.get("action") == "replace"
            and form.cleaned_data.get("replacement")
        ]
        if len(chosen) != len(set(chosen)):
            raise forms.ValidationError(
                "Une nouvelle ligne ne remplace qu'une seule tâche."
            )


GoneLineFormSet = modelformset_factory(
    Todo, form=GoneLineForm, formset=BaseGoneLineFormSet, extra=0
)
