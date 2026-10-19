from django import forms
from django.urls import reverse_lazy

from .models import Project, NotePart, Note


class NoteSearchForm(forms.Form):
    projects = forms.ModelMultipleChoiceField(
        queryset=Project.objects.all().order_by("name"),
        widget=forms.CheckboxSelectMultiple(attrs={
            "hx-post": reverse_lazy("note_taking:get_subjects"),
            "hx-target": "#subjects-block",
            "hx-trigger": "change",
            "hx-include": "closest form",
        }),
        required=False,
        label="Projet(s)"
    )
    subjects = forms.MultipleChoiceField(
        choices=[],
        widget=forms.CheckboxSelectMultiple(),
        required=False,
        label="Sujet(s)"
    )
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        subjects = (
            NotePart.objects
            .exclude(subject__isnull=True)
            .exclude(subject__exact="")
            .values_list("subject", flat=True)
            .distinct()
        )
        subjects = sorted(subjects, key=str.lower)

        self.fields["subjects"].choices = [(s, s) for s in subjects]

class NewNoteForm(forms.ModelForm):
    class Meta:
        model = Note
        fields = ["date", "raw"]