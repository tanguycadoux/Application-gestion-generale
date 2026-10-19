from django import forms
from django.urls import reverse_lazy

from core.models import Project

from .models import Note, NotePart


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

        parts = NotePart.objects.exclude(subject__isnull=True).exclude(
            subject__exact=""
        )
        if projects:
            parts = parts.filter(project_id__in=projects)
        subjects = parts.values_list("subject", flat=True).distinct()

        self.fields["subjects"].choices = [
            (s, s) for s in sorted(subjects, key=str.lower)
        ]


class NewNoteForm(forms.ModelForm):
    class Meta:
        model = Note
        fields = ["date", "raw"]
