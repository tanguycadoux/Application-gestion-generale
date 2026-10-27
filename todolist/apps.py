from django.apps import AppConfig
from django.db.models import Q

from core.app_registry import NavItem, NavSection, ProjectUsage, SectionUsage


class TodolistConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "todolist"
    nav_section = NavSection(
        "Tâches",
        20,
        (
            NavItem("todolist:index", "Calendrier", "calendar_month"),
            NavItem("todolist:todo_list", "Liste des tâches", "checklist"),
        ),
    )
    project_usages = (
        ProjectUsage(
            "todos", "tâche", "tâches", exclude=Q(todos__note_state="dismissed")
        ),
    )

    section_usages = (
        SectionUsage(
            "todos", "tâche", "tâches", exclude=Q(todos__note_state="dismissed")
        ),
    )

    def ready(self):
        from . import receivers  # noqa: F401
