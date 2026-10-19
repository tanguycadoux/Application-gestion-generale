from django import forms
from django.urls import reverse_lazy

from core.models import Project, Subject

from .models import Note


class NoteSearchForm(forms.Form):
    projects = forms.ModelMultipleChoiceField(
        queryset=Project.objects.all().order_by("name"),
        widget=forms.CheckboxSelectMultiple(
            attrs={
                "hx-post": reverse_lazy("note_taking:get_subjects"),
                "hx-target": "#subjects-block",
                "hx-trigger": "change",
                "hx-include": "closest form",
            }
        ),
        required=False,
        label="Projet(s)",
    )
    subjects = forms.MultipleChoiceField(
        choices=[],
        widget=forms.CheckboxSelectMultiple(),
        required=False,
        label="Sujet(s)",
    )

    def __init__(self, *args, projects=None, **kwargs):
        """`projects` : identifiants de projets limitant les sujets proposés."""
        super().__init__(*args, **kwargs)

        # Seuls les sujets utilisés par des note parts sont proposés.
        subjects = Subject.objects.filter(note_parts__isnull=False)
        if projects:
            subjects = subjects.filter(note_parts__project_id__in=projects)
        names = subjects.values_list("name", flat=True).distinct()

        self.fields["subjects"].choices = [
            (name, name) for name in sorted(names, key=str.lower)
        ]


class NewNoteForm(forms.ModelForm):
    class Meta:
        model = Note
        fields = ["date", "raw"]
