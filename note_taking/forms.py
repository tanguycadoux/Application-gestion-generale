from django import forms
from django.urls import reverse_lazy

from core.models import Project, Subject

from .exceptions import NoteParseError
from .models import Note
from .qmd.files import split_front_matter


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
        fields = ["date", "body"]

    def clean(self):
        """Retire un éventuel bloc d'en-tête du corps, après en avoir vérifié la date."""
        cleaned_data = super().clean()
        try:
            metadata, body = split_front_matter(cleaned_data.get("body", ""))
        except NoteParseError as e:
            self.add_error("body", str(e))
            return cleaned_data

        header_date = metadata.get("date")
        note_date = cleaned_data.get("date")
        if header_date and note_date and header_date != str(note_date):
            self.add_error(
                "body",
                f"La date du bloc d'en-tête ({header_date}) ne correspond pas "
                "à la date de la note.",
            )
        cleaned_data["body"] = body
        return cleaned_data
