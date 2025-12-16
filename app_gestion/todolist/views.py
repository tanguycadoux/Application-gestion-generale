from django.http import JsonResponse
from django.shortcuts import render
from django.urls import reverse_lazy
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.generic import ListView, DetailView, CreateView, UpdateView, DeleteView

from .models import Todo, Tag
from .forms import TodoForm

import json


def index(request):
    context = {}

    return render(request, "todolist/index.html", context)


class TodoListView(ListView):
    model = Todo
    template_name = "todolist/todo_list.html"

    def get_queryset(self):
        return Todo.objects.filter(parent__isnull=True).order_by('due_date')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        qs = self.get_queryset()

        context['todo_pending'] = qs.filter(completed=False)
        context['todo_completed'] = qs.filter(completed=True)
        
        context['today'] = timezone.localdate()
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


class TodoDeleteView(DeleteView):
    model = Todo
    template_name = "todolist/todo_confirm_delete.html"
    success_url = reverse_lazy("todolist:todo_list")


def toggle_todo(request, pk):
    if request.method == "POST":
        data = json.loads(request.body)
        todo = Todo.objects.get(pk=pk)
        todo.completed = data.get("completed", False)
        todo.save()
        return JsonResponse({"status": "ok"})
