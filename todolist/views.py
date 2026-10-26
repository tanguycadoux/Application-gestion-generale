import json
from datetime import date

from django.contrib import messages
from django.contrib.messages.views import SuccessMessageMixin
from django.db import transaction
from django.http import Http404, HttpResponseRedirect, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.template.loader import render_to_string
from django.urls import reverse_lazy
from django.views.decorators.http import require_POST
from django.views.generic import (
    CreateView,
    DeleteView,
    DetailView,
    UpdateView,
)

from core.month_calendar import requested_month
from core.templatetags.ui import date_text
from note_taking.models import Note

from .forms import GoneLineFormSet, NoteReviewFormSet, TodoForm
from .gantt import gantt_chart
from .models import Todo
from .services import note_lines, note_todos_to_review, remove_task, replace_task
from .task_calendar import task_calendar
from .tree import TaskGroup, descendant_rows, task_groups, task_rows


def index(request):
    """Accueil : calendrier des tâches du mois demandé (?mois=AAAA-MM), #167."""
    today, year, month = requested_month(request.GET.get("mois", ""))
    return render(
        request,
        "todolist/index.html",
        {"calendar": task_calendar(year, month, today)},
    )


def parse_date_param(value: str):
    """Date au format AAAA-MM-JJ, ou None."""
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


def todo_list(request):
    """Tableau des tâches (#166) : un groupe par tâche racine, en cours d'abord,
    les arbres dont la racine est terminée dans une section repliée."""
    groups = task_groups()
    return render(
        request,
        "todolist/todo_list.html",
        {
            "pending_groups": [g for g in groups if not g.root.done],
            "done_groups": [g for g in groups if g.root.done],
        },
    )


def with_subtasks(count: int) -> str:
    """« et sa sous-tâche », « et ses 3 sous-tâches », ou rien (#223)."""
    if count == 0:
        return ""
    return " et sa sous-tâche" if count == 1 else f" et ses {count} sous-tâches"


class TodoDetailView(DetailView):
    model = Todo
    template_name = "todolist/todo_detail.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        todo = self.object
        context["origin_note"] = (
            Note.objects.filter(date=todo.note_part_date).first()
            if todo.created_from_note
            else None
        )
        context["children_groups"] = [TaskGroup(todo, descendant_rows(todo))]
        context["children"] = context["children_groups"][0].rows
        context["gantt"] = gantt_chart(todo)
        # Les sous-tâches sont supprimées avec la tâche : la confirmation le dit (#223).
        context["delete_confirm"] = (
            f"Supprimer définitivement la tâche « {todo.title} »"
            f"{with_subtasks(len(context['children']))} ?"
        )
        return context


class TodoCreateView(SuccessMessageMixin, CreateView):
    model = Todo
    form_class = TodoForm
    template_name = "todolist/todo_form.html"
    success_url = reverse_lazy("todolist:todo_list")
    success_message = "La tâche « %(title)s » est créée."

    def get_initial(self):
        initial = super().get_initial()
        due = parse_date_param(self.request.GET.get("due", ""))
        if due:
            initial["due_date"] = due
        parent_id = self.request.GET.get("parent")
        if parent_id:
            try:
                parent = Todo.objects.get(pk=parent_id)
                initial["parent"] = parent
                initial["project"] = parent.project
                initial["due_date"] = parent.due_date
            except Todo.DoesNotExist:
                pass
        return initial


class TodoUpdateView(SuccessMessageMixin, UpdateView):
    model = Todo
    form_class = TodoForm
    template_name = "todolist/todo_form.html"
    success_url = reverse_lazy("todolist:todo_list")
    success_message = "La tâche « %(title)s » est modifiée."


class TodoDeleteView(SuccessMessageMixin, DeleteView):
    """Supprime une tâche ; la confirmation se fait par popover (data-confirm)."""

    model = Todo
    http_method_names = ["post"]
    success_url = reverse_lazy("todolist:todo_list")

    def form_valid(self, form):
        # Compté avant la suppression, qui emporte les sous-tâches (#223).
        self.subtasks = self.object.descendants_count()
        success_url = self.get_success_url()
        # Une tâche issue d'une note est écartée, pas supprimée (#240).
        remove_task(self.object)
        messages.success(self.request, self.get_success_message(form.cleaned_data))
        return HttpResponseRedirect(success_url)

    def get_success_message(self, cleaned_data):
        title = self.object.title
        if self.subtasks:
            return (
                f"La tâche « {title} »{with_subtasks(self.subtasks)} sont supprimées."
            )
        return f"La tâche « {title} » est supprimée."


@require_POST
def toggle_todo(request, pk):
    todo = get_object_or_404(Todo, pk=pk)

    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        data = None
    if not isinstance(data, dict):
        return JsonResponse({"error": "Corps de requête JSON invalide."}, status=400)

    completed = bool(data.get("completed"))
    if todo.children.exists():
        # Un parent se coche à la main ; son avancement reste calculé (#164).
        todo.done = completed
    else:
        # Décocher rend l'avancement d'avant la coche (#237).
        todo.progress = 100 if completed else todo.progress_before_done
    todo.save()
    toggled_ids = [todo.pk, *todo.updated_ancestor_ids]
    # Lignes à jour, que la liste remplace sans recharger la page (#189).
    rows = {
        str(pk): render_to_string(
            "todolist/task_row.html", {"row": row}, request
        ).strip()
        for pk, row in task_rows(toggled_ids).items()
    }
    return JsonResponse({"status": "ok", "toggled_ids": toggled_ids, "rows": rows})


def note_review(request, note_date: str):
    """Bilan des tâches à revoir d'une note (#239, #240), puis retour à la note.

    - Tâches dont la ligne est dans la note (nouvelles, ou laissées « plus
      tard ») : échéance, priorité, projet et sujet se règlent aussitôt.
    - Tâches dont la ligne a disparu : la garder, l'écarter, ou la remplacer par
      la tâche d'une nouvelle ligne.

    Enregistrer les rend revues ; sans tâche à revoir, retour direct à la note.
    """
    day = parse_date_param(note_date)
    if day is None:
        raise Http404("Date invalide.")
    note = get_object_or_404(Note, date=day)
    todos = list(
        note_todos_to_review(day).select_related("project", "subject").order_by("pk")
    )
    if not todos:
        return redirect("note_taking:note_detail", pk=note.pk)

    lines = note_lines(note.parts.prefetch_related("tags"))
    new_ids = [t.pk for t in todos if (t.note_path, t.note_part_text) in lines]
    gone_ids = [t.pk for t in todos if t.pk not in new_ids]
    new_todos = Todo.objects.filter(pk__in=new_ids).order_by("pk")
    data = request.POST or None
    new_formset = NoteReviewFormSet(data, queryset=new_todos, prefix="new")
    gone_formset = GoneLineFormSet(
        data,
        queryset=Todo.objects.filter(pk__in=gone_ids).order_by("pk"),
        prefix="gone",
        form_kwargs={"replacements": new_todos},
    )

    if request.method == "POST" and new_formset.is_valid() and gone_formset.is_valid():
        # Une tâche nouvelle qui en remplace une autre disparaît : ses réglages
        # ne comptent pas, l'ancienne garde les siens.
        replaced = {
            form.cleaned_data["replacement"].pk
            for form in gone_formset
            if form.cleaned_data["action"] == "replace"
        }
        with transaction.atomic():
            for form in new_formset:
                if form.instance.pk not in replaced:
                    todo = form.save(commit=False)
                    todo.note_state = Todo.NoteState.REVIEWED
                    todo.save()
            save_gone_lines(gone_formset)
        messages.success(
            request,
            f"Les tâches de la note du {date_text(day, 'moyen')} sont enregistrées.",
        )
        return redirect("note_taking:note_detail", pk=note.pk)
    return render(
        request,
        "todolist/note_review.html",
        {"note": note, "new_formset": new_formset, "gone_formset": gone_formset},
    )


def save_gone_lines(formset) -> None:
    """Applique le choix fait pour chaque tâche dont la ligne a disparu."""
    for form in formset:
        todo, action = form.instance, form.cleaned_data["action"]
        if action == "keep":
            todo.note_state = Todo.NoteState.DETACHED
            todo.save()
        elif action == "dismiss":
            remove_task(todo)
        else:
            replace_task(todo, form.cleaned_data["replacement"])
