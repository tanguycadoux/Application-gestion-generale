from django import forms
from django.forms import modelformset_factory

from core.forms import SectionPathField, section_path_text
from core.sections import section_for

from .models import Todo


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
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
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
