from django.apps import AppConfig

from .app_registry import NavItem, NavSection


class CoreConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "core"
    nav_section = NavSection(
        "Projets", 30, (NavItem("core:projects", "Liste des projets", "folder"),)
    )
