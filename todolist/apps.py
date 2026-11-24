from django.apps import AppConfig
from django.db.models import Q

from core.app_registry import (
    DashboardBlock,
    NavItem,
    NavSection,
    ProjectUsage,
    SectionUsage,
    WeekBlock,
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
        # Les tâches terminées sont comptées : la liste les montre aussi (`state=all`).
        SectionUsage(
            "tasks",
            "tâche",
            "tâches",
            url_name="todolist:task_list",
            query="path={pk}&state=all",
            exclude=Q(tasks__note_state="dismissed"),
        ),
    )

    def ready(self):
        from . import dashboard, progress, receivers, week  # noqa: F401

        self.week_blocks = (
            WeekBlock("Tâches", 20, "todolist/week_tasks.html", week.week_tasks),
        )

        self.dashboard_blocks = (
            DashboardBlock(
                "Tâches à échéance proche",
                20,
                "todolist/dashboard_due.html",
                dashboard.due_tasks,
            ),
            DashboardBlock(
                "À traiter",
                30,
                "todolist/dashboard_pending.html",
                dashboard.pending,
            ),
        )
