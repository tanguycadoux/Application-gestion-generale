from django.urls import path

from core import converters  # noqa: F401  (le convertisseur `date`)

from .views import (
    TodoCreateView,
    TodoDeleteView,
    TodoDetailView,
    TodoUpdateView,
    index,
    note_review,
    restore_todo,
    todo_list,
    toggle_todo,
)

app_name = "todolist"

urlpatterns = [
    path("", index, name="index"),
    path("list/", todo_list, name="todo_list"),
    path("new/", TodoCreateView.as_view(), name="todo_create"),
    path("<int:pk>/", TodoDetailView.as_view(), name="todo_detail"),
    path("<int:pk>/edit/", TodoUpdateView.as_view(), name="todo_edit"),
    path("<int:pk>/delete/", TodoDeleteView.as_view(), name="todo_delete"),
    path("<int:pk>/toggle/", toggle_todo, name="todo_toggle"),
    path("<int:pk>/restore/", restore_todo, name="todo_restore"),
    path("notes/<date:note_date>/review/", note_review, name="note_review"),
]
