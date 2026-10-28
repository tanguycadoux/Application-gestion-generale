from django import forms
from django.urls import reverse_lazy

from core.models import Project, Section
from core.sections import path_labels, with_ancestors

from .exceptions import NoteParseError
from .models import Note
from .qmd.files import split_front_matter


class NoteSearchForm(forms.Form):
    q = forms.CharField(
        required=False,
        label="Texte",
        widget=forms.TextInput(attrs={"type": "search", "placeholder": "Rechercher…"}),
    )
    projects = forms.ModelMultipleChoiceField(
        queryset=Project.objects.all().order_by("name"),
        widget=forms.CheckboxSelectMultiple(
            attrs={
                "data-hx-get": reverse_lazy("note_taking:get_subjects"),
                "data-hx-target": "#subjects-block",
                "data-hx-trigger": "change",
                "data-hx-include": "closest form",
            }
        ),
        required=False,
        label="Projet(s)",
    )
    subjects = forms.MultipleChoiceField(
        choices=[],
        widget=forms.CheckboxSelectMultiple(),
        required=False,
        label="Chemin(s)",
    )

    def __init__(self, *args, projects=None, **kwargs):
        """`projects` : identifiants de projets limitant les sujets proposés."""
        super().__init__(*args, **kwargs)

        # Seuls les chemins utilisés par des note parts sont proposés, avec leurs
        # parents : choisir un niveau cherche aussi ses descendants (#296).
        used = Section.objects.filter(note_parts__isnull=False)
        if projects:
            used = used.filter(project_id__in=projects)
        labels = path_labels()
        pks = with_ancestors(used.values_list("pk", flat=True))

        self.fields["subjects"].choices = sorted(
            ((str(pk), labels[pk]) for pk in pks),
            key=lambda choice: choice[1].casefold(),
        )


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
