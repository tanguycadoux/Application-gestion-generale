from django import forms

from core.models import Project, Section

from .exceptions import NoteParseError
from .models import Note
from .qmd.files import split_front_matter


class NoteSearchForm(forms.Form):
    """Les champs de la page de recherche, lus dans l'adresse (#199).

    `subjects` vient des cases de l'arbre des chemins (#302) : le formulaire ne les
    affiche pas, il valide les niveaux choisis.
    """

    q = forms.CharField(
        required=False,
        label="Texte",
        widget=forms.TextInput(attrs={"type": "search", "placeholder": "Rechercher…"}),
    )
    projects = forms.ModelMultipleChoiceField(
        queryset=Project.objects.all().order_by("name"),
        widget=forms.CheckboxSelectMultiple(),
        required=False,
        label="Projets",
    )
    subjects = forms.ModelMultipleChoiceField(
        queryset=Section.objects.all(),
        required=False,
        label="Chemins",
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
