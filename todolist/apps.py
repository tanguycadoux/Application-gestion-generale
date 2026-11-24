from django.apps import AppConfig
from django.db.models import Q

from core.app_registry import (
    DashboardBlock,
    NavItem,
    NavSection,
    ProjectBlock,
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
        from . import (  # noqa: F401 (récepteurs)
            dashboard,
            progress,
            project_blocks,
            receivers,
        )

        self.project_blocks = (
            ProjectBlock(
                "project-tasks",
                "Tâches",
                20,
                "todolist/project_tasks.html",
                project_blocks.tasks_block,
            ),
            ProjectBlock(
                "project-timeline",
                "Frise des tâches",
                50,
                "todolist/project_timeline.html",
                project_blocks.timeline_block,
            ),
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
