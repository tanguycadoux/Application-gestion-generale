import json
from datetime import date

from django.contrib.messages.views import SuccessMessageMixin
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, render
from django.urls import reverse_lazy
from django.views.decorators.http import require_POST
from django.views.generic import (
    CreateView,
    DeleteView,
    DetailView,
    UpdateView,
)

from core.month_calendar import requested_month
from note_taking.models import Note

from .forms import TodoForm
from .gantt import gantt_chart
from .models import Todo
from .task_calendar import task_calendar
from .tree import TaskGroup, descendant_rows, task_groups


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
    groups = task_groups(Todo.objects.filter(parent__isnull=True))
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


class TodoCreateView(CreateView):
    model = Todo
    form_class = TodoForm
    template_name = "todolist/todo_form.html"
    success_url = reverse_lazy("todolist:todo_list")

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


class TodoUpdateView(UpdateView):
    model = Todo
    form_class = TodoForm
    template_name = "todolist/todo_form.html"
    success_url = reverse_lazy("todolist:todo_list")


class TodoDeleteView(SuccessMessageMixin, DeleteView):
    """Supprime une tâche ; la confirmation se fait par popover (data-confirm)."""

    model = Todo
    http_method_names = ["post"]
    success_url = reverse_lazy("todolist:todo_list")

    def form_valid(self, form):
        # Compté avant la suppression, qui emporte les sous-tâches (#223).
        self.subtasks = self.object.descendants_count()
        return super().form_valid(form)

    def get_success_message(self, cleaned_data):
        title = self.object.title
        if self.subtasks:
            return f"La tâche « {title} »{with_subtasks(self.subtasks)} ont été supprimées."
        return f"La tâche « {title} » a été supprimée."


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
        todo.progress = 100 if completed else 0
    todo.save()
    return JsonResponse(
        {"status": "ok", "toggled_ids": [todo.pk, *todo.updated_ancestor_ids]}
    )
