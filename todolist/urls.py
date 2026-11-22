from django.urls import path

from core import converters  # noqa: F401  (le convertisseur `date`)

from .views import (
    TaskCreateView,
    TaskDeleteView,
    TaskDetailView,
    TaskUpdateView,
    index,
    note_review,
    parent_choices_view,
    restore_task_view,
    task_list,
    toggle_task,
)

app_name = "todolist"

urlpatterns = [
    path("", index, name="index"),
    path("list/", task_list, name="task_list"),
    path("new/", TaskCreateView.as_view(), name="task_create"),
    path("parent-choices/", parent_choices_view, name="parent_choices"),
    path("<int:pk>/", TaskDetailView.as_view(), name="task_detail"),
    path("<int:pk>/edit/", TaskUpdateView.as_view(), name="task_edit"),
    path("<int:pk>/delete/", TaskDeleteView.as_view(), name="task_delete"),
    path("<int:pk>/toggle/", toggle_task, name="task_toggle"),
    path("<int:pk>/restore/", restore_task_view, name="task_restore"),
    path("notes/<date:note_date>/review/", note_review, name="note_review"),
]
