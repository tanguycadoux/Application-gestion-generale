import json

from django.contrib.messages.views import SuccessMessageMixin
from django.db.models import Min, Q
from django.db.models.functions import Coalesce
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, render
from django.urls import reverse_lazy
from django.utils import timezone
from django.views.decorators.http import require_POST
from django.views.generic import (
    CreateView,
    DeleteView,
    DetailView,
    ListView,
    UpdateView,
)

from .forms import TodoForm
from .models import Todo


def index(request):
    context = {}

    return render(request, "todolist/index.html", context)


class TodoListView(ListView):
    model = Todo
    template_name = "todolist/todo_list.html"

    def get_queryset(self):
        return (
            Todo.objects.filter(parent__isnull=True)
            .annotate(
                earliest_child_due_date=Min(
                    "children__due_date", filter=Q(children__completed=False)
                ),
                sort_due_date=Coalesce(
                    Min("children__due_date", filter=Q(children__completed=False)),
                    "due_date",
                ),
            )
            .order_by("sort_due_date")
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        qs = self.get_queryset()

        context["todo_pending"] = qs.filter(completed=False)
        context["todo_completed"] = qs.filter(completed=True)

        context["today"] = timezone.localdate()
        return context


class TodoDetailView(DetailView):
    model = Todo
    template_name = "todolist/todo_detail.html"


class TodoCreateView(CreateView):
    model = Todo
    form_class = TodoForm
    template_name = "todolist/todo_form.html"
    success_url = reverse_lazy("todolist:todo_list")

    def get_initial(self):
        initial = super().get_initial()
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
    """Supprime une TODO ; la confirmation se fait par popover (data-confirm)."""

    model = Todo
    http_method_names = ["post"]
    success_url = reverse_lazy("todolist:todo_list")
    success_message = "La TODO « %(title)s » a été supprimée."

    def get_success_message(self, cleaned_data):
        return self.success_message % {"title": self.object.title}


@require_POST
def toggle_todo(request, pk):
    todo = get_object_or_404(Todo, pk=pk)

    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        data = None
    if not isinstance(data, dict):
        return JsonResponse({"error": "Corps de requête JSON invalide."}, status=400)

    completed = bool(data.get("completed", False))
    force = bool(data.get("force", False))

    incomplete_children = todo.children.filter(completed=False)
    if completed and not force and incomplete_children.exists():
        return JsonResponse(
            {
                "status": "needs_confirmation",
                "message": "Cette tâche contient des sous-tâches non complétées.",
                "children_count": incomplete_children.count(),
            }
        )

    toggled_ids = todo.set_completed(completed)
    return JsonResponse({"status": "ok", "toggled_ids": toggled_ids})
