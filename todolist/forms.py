from django import forms

from .models import Todo


class TodoForm(forms.ModelForm):
    class Meta:
        model = Todo
        fields = [
            "title",
            "description",
            "progress",
            "priority",
            "due_date",
            "project",
            "subject",
            "tags",
            "parent",
        ]
        widgets = {
            "due_date": forms.DateInput(format=r"%Y-%m-%d", attrs={"type": "date"}),
            "progress": forms.NumberInput(attrs={"min": 0, "max": 100, "step": 5}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["due_date"].input_formats = [r"%Y-%m-%d"]
