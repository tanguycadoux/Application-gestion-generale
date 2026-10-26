from django.apps import AppConfig
from django.db.models import Q

from core.app_registry import HomeLink, ProjectUsage


class TodolistConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "todolist"
    home_link = HomeLink("todolist:index", "Tâches", "checklist")
    project_usages = (
        ProjectUsage(
            "todos", "tâche", "tâches", exclude=Q(todos__note_state="dismissed")
        ),
    )

    def ready(self):
        from . import receivers  # noqa: F401
