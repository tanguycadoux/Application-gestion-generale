from django.apps import AppConfig
from django.db.models import Q

from core.app_registry import (
    DashboardBlock,
    NavItem,
    NavSection,
    ProjectUsage,
    SectionUsage,
)


class TodolistConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "todolist"
    nav_section = NavSection(
        "Tâches",
        20,
        (
            NavItem("todolist:index", "Calendrier", "calendar_month"),
            NavItem("todolist:task_list", "Liste des tâches", "checklist"),
        ),
    )
    project_usages = (
        ProjectUsage(
            "tasks", "tâche", "tâches", exclude=Q(tasks__note_state="dismissed")
        ),
    )

    section_usages = (
        SectionUsage(
            "tasks", "tâche", "tâches", exclude=Q(tasks__note_state="dismissed")
        ),
    )

    def ready(self):
        from . import dashboard, progress, receivers  # noqa: F401

        self.dashboard_blocks = (
            DashboardBlock(
                "Tâches à échéance proche",
                20,
                "todolist/dashboard_due.html",
                dashboard.due_tasks,
            ),
        )
