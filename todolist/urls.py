from django.urls import path

from .views import (
    index, toggle_todo,
    TodoListView, TodoDetailView,
    TodoCreateView, TodoUpdateView,
    TodoDeleteView
)

app_name = "todolist"

urlpatterns = [
    path("", index, name="index"),
    path('todos', TodoListView.as_view(), name='todo_list'),
    path('todo/<int:pk>/', TodoDetailView.as_view(), name='todo_detail'),
    path('todo/new/', TodoCreateView.as_view(), name='todo_create'),
    path('todo/<int:pk>/edit/', TodoUpdateView.as_view(), name='todo_edit'),
    path('todo/<int:pk>/delete/', TodoDeleteView.as_view(), name='todo_delete'),
    path("todo/<int:pk>/toggle/", toggle_todo, name="todo_toggle"),
]
