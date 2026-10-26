from django.apps import AppConfig

from core.app_registry import HomeLink, ProjectUsage


class NoteTakingConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "note_taking"
    home_link = HomeLink("note_taking:index", "Prise de notes", "docs")
    project_usages = (ProjectUsage("note_parts__note", "note", "notes"),)
