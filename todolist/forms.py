from django import forms

from .models import Todo, Project, Tag


class TodoForm(forms.ModelForm):
    class Meta:
        model = Todo
        fields = [
            'title', 'description', 'completed',
            'priority', 'due_date',
            'project', 'tags', 'parent'
        ]
        widgets = {
            'due_date': forms.DateInput(
                format=r'%Y-%m-%d',
                attrs={'type': 'date'}
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['due_date'].input_formats = [r'%Y-%m-%d']
