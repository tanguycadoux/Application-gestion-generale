from collections.abc import Mapping

from django import forms
from django.forms import modelformset_factory
from django.urls import reverse

from core.forms import SectionPathField, TagSelectMultiple, section_path_text
from core.sections import section_for

from .models import Task
from .parent_choices import ParentContext, parent_choices


class ParentSelect(forms.Select):
    """Choix de la tâche parente (#390) : options groupées, libellé complet d'une
    option coupée en infobulle, case des tâches terminées, rechargé par htmx.

    Les options se calculent à l'affichage seulement, d'après `parent_data` (les
    valeurs saisies) : un formulaire envoyé et valide n'en a pas besoin.
    """

    template_name = "todolist/widgets/parent_select.html"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.parent_data: Mapping = {}
        self.task: Task | None = None
        self.titles: dict[str, str] = {}

    def create_option(
        self, name, value, label, selected, index, subindex=None, attrs=None
    ):
        option = super().create_option(
            name, value, label, selected, index, subindex, attrs
        )
        title = self.titles.get(str(value))
        if title:
            option["attrs"]["title"] = title
        return option

    def get_context(self, name, value, attrs):
        result = parent_choices(ParentContext.from_data(self.parent_data, self.task))
        self.choices, self.titles = result.choices, result.titles
        context = super().get_context(name, value, attrs)
        context["widget"]["show_done"] = self.parent_data.get("parent_show_done") == "1"
        url = reverse("todolist:parent_choices")
        context["widget"]["choices_url"] = (
            f"{url}?task={self.task.pk}" if self.task else url
        )
        return context


class SectionPathForm(forms.ModelForm):
    """Formulaire d'une tâche dont le chemin se saisit en texte (#298), sous le
    projet choisi : un chemin inconnu est créé à l'enregistrement, pas avant."""

    section_path = SectionPathField()

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance.pk:
            self.initial["section_path"] = section_path_text(self.instance.section)

    def clean(self):
        cleaned_data = super().clean()
        if cleaned_data.get("section_path") and not cleaned_data.get("project"):
            self.add_error(
                "section_path", "Un chemin se range sous un projet : choisir le projet."
            )
        return cleaned_data

    def save(self, commit=True):
        task = super().save(commit=False)
        project = self.cleaned_data["project"]
        # Sans projet (#385), pas de chemin.
        task.section = (
            section_for(project, self.cleaned_data["section_path"]) if project else None
        )
        if commit:
            task.save()
            self.save_m2m()
        return task


class TaskForm(SectionPathForm):
    class Meta:
        model = Task
        fields = [
            "title",
            "description",
            "progress",
            "done",
            "priority",
            "due_date",
            "no_due_date",
            "project",
            "section_path",
            "tags",
            "parent",
        ]
        widgets = {
            "due_date": forms.DateInput(format=r"%Y-%m-%d", attrs={"type": "date"}),
            "progress": forms.NumberInput(attrs={"min": 0, "max": 100}),
            "parent": ParentSelect,
            "tags": TagSelectMultiple,
        }

    def __init__(self, *args, parent_data=None, **kwargs):
        """`parent_data` : projet, chemin, parent et case des terminées tels que
        saisis, quand htmx recharge le choix du parent (#390)."""
        super().__init__(*args, **kwargs)
        self.set_up_parent(parent_data)
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

    def set_up_parent(self, parent_data):
        """Le parent se choisit parmi les tâches les plus proches de ce qui est
        saisi (#390). Seul l'affichage est trié : toute tâche reste acceptée, sauf
        une boucle (`Task.clean`)."""
        widget = self.fields["parent"].widget
        widget.task = self.instance if self.instance.pk else None
        if self.is_bound:
            widget.parent_data = self.data
        elif parent_data is not None:
            widget.parent_data = parent_data
            self.initial["parent"] = parent_data.get("parent")
        else:
            widget.parent_data = self.initial


class NoteReviewForm(SectionPathForm):
    """Ligne du bilan d'une note (#239) : ce qui se règle juste après la création
    d'une tâche, l'échéance surtout."""

    class Meta:
        model = Task
        fields = ["due_date", "priority", "project", "section_path"]
        widgets = {
            "due_date": forms.DateInput(format=r"%Y-%m-%d", attrs={"type": "date"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["due_date"].input_formats = [r"%Y-%m-%d"]


NoteReviewFormSet = modelformset_factory(Task, form=NoteReviewForm, extra=0)


PATH_SEPARATOR = " › "


def same_text(text: str) -> str:
    """Texte d'une ligne comparé sans casse ni blancs en trop (#382)."""
    return " ".join(text.split()).casefold()


def path_levels(path: str) -> list[str]:
    return path.split(PATH_SEPARATOR) if path else []


def common_ends(old: list[str], new: list[str]) -> tuple[int, int]:
    """Nombre de niveaux communs au début, puis à la fin, de deux chemins."""
    shortest = min(len(old), len(new))
    start = 0
    while start < shortest and old[start] == new[start]:
        start += 1
    end = 0
    while end < shortest - start and old[-1 - end] == new[-1 - end]:
        end += 1
    return start, end


def same_text_replacements(gone, new) -> dict[int, Task]:
    """Pour chaque tâche dont la ligne a disparu, la nouvelle tâche de même texte
    à proposer en remplacement (#382), par clé de la tâche disparue.

    Une nouvelle tâche n'est proposée qu'une fois. Entre plusieurs de même texte,
    celle dont le chemin a le plus de niveaux communs avec l'ancien, à la fin
    puis au début : un titre renommé au-dessus de deux lignes de même texte.
    """
    free = list(new)
    proposals: dict[int, Task] = {}
    for task in gone:
        text = same_text(task.note_line_text)
        candidates = [t for t in free if same_text(t.note_line_text) == text]
        if not candidates:
            continue
        levels = path_levels(task.note_path)

        def closeness(other: Task, levels=levels) -> tuple[int, int]:
            start, end = common_ends(levels, path_levels(other.note_path))
            return end, start

        best = max(candidates, key=closeness)
        proposals[task.pk] = best
        free.remove(best)
    return proposals


def path_changes(old: str, new: str) -> tuple[list, list]:
    """Niveaux de l'ancien et du nouveau chemin, chacun en couple (niveau, changé) :
    à même profondeur, niveau par niveau ; sinon, ce qui reste commun au début et à
    la fin n'a pas changé (#382)."""
    old_levels, new_levels = path_levels(old), path_levels(new)
    if not new_levels:
        return [(level, False) for level in old_levels], []
    if len(old_levels) == len(new_levels):
        return (
            [(o, o != n) for o, n in zip(old_levels, new_levels, strict=True)],
            [(n, o != n) for o, n in zip(old_levels, new_levels, strict=True)],
        )
    start, end = common_ends(old_levels, new_levels)

    def marked(levels: list[str]) -> list[tuple[str, bool]]:
        return [
            (level, start <= index < len(levels) - end)
            for index, level in enumerate(levels)
        ]

    return marked(old_levels), marked(new_levels)


class GoneLineForm(forms.ModelForm):
    """Ligne du bilan d'une tâche dont la ligne a disparu de la note (#240) : la
    garder, l'écarter, ou la remplacer par la tâche d'une nouvelle ligne.

    Une nouvelle tâche de même texte (`proposed`, #382), le plus souvent après un
    titre renommé au-dessus de la ligne, est choisie d'avance en remplacement.
    """

    ACTIONS = [
        ("keep", "La garder"),
        ("dismiss", "L'écarter"),
        ("replace", "La remplacer par"),
    ]

    action = forms.ChoiceField(label="Que faire", choices=ACTIONS, initial="keep")
    replacement = forms.ModelChoiceField(
        label="Nouvelle ligne",
        queryset=Task.objects.none(),
        required=False,
        empty_label="—",
        # Pleine largeur de sa colonne : un long chemin ne pousse pas le tableau
        # hors de la page, l'option choisie est coupée (#382).
        widget=forms.Select(attrs={"class": "w-full"}),
    )

    class Meta:
        model = Task
        fields: list[str] = []

    def __init__(self, *args, replacements=None, proposed=None, **kwargs):
        super().__init__(*args, **kwargs)
        if replacements is not None:
            self.fields["replacement"].queryset = replacements
        # Le titre seul est ambigu : le chemin dit où est la ligne dans la note.
        self.fields["replacement"].label_from_instance = lambda task: " › ".join(
            part for part in (task.note_path, task.note_line_text) if part
        )
        if proposed is not None:
            self.initial |= {"action": "replace", "replacement": proposed.pk}
        # Ancien chemin, et en face celui de la tâche de même texte (#382).
        self.old_path, self.new_path = path_changes(
            self.instance.note_path, proposed.note_path if proposed else ""
        )

    def clean(self):
        cleaned_data = super().clean()
        if cleaned_data.get("action") == "replace" and not cleaned_data.get(
            "replacement"
        ):
            self.add_error("replacement", "Choisir la nouvelle ligne qui la remplace.")
        return cleaned_data


class BaseGoneLineFormSet(forms.BaseModelFormSet):
    proposals: dict[int, Task] | None = None

    def get_form_kwargs(self, index):
        """Chaque tâche disparue reçoit la nouvelle tâche de même texte (#382)."""
        kwargs = super().get_form_kwargs(index)
        gone = self.get_queryset()
        if index is not None and index < len(gone):
            if self.proposals is None:
                self.proposals = same_text_replacements(
                    gone, kwargs.get("replacements") or []
                )
            kwargs["proposed"] = self.proposals.get(gone[index].pk)
        return kwargs

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
    Task, form=GoneLineForm, formset=BaseGoneLineFormSet, extra=0
)
