from django import forms
from django.forms import modelformset_factory

from .models import Todo


class TodoForm(forms.ModelForm):
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
            "subject",
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


class NoteReviewForm(forms.ModelForm):
    """Ligne du bilan d'une note (#239) : ce qui se règle juste après la création
    d'une tâche, l'échéance surtout."""

    class Meta:
        model = Todo
        fields = ["due_date", "priority", "project", "subject"]
        widgets = {
            "due_date": forms.DateInput(format=r"%Y-%m-%d", attrs={"type": "date"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["due_date"].input_formats = [r"%Y-%m-%d"]


NoteReviewFormSet = modelformset_factory(Todo, form=NoteReviewForm, extra=0)
