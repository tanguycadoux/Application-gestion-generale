from django.apps import AppConfig

from core.app_registry import (
    DashboardBlock,
    NavItem,
    NavSection,
    ProjectUsage,
    SectionRenamer,
    SectionUsage,
)


class NoteTakingConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "note_taking"
    nav_section = NavSection(
        "Notes",
        10,
        (
            NavItem("note_taking:index", "Calendrier", "calendar_month"),
            NavItem("note_taking:note_today", "Note du jour", "today"),
            NavItem("note_taking:notes_list", "Les notes", "docs"),
            NavItem("note_taking:notes_search", "Recherche de notes", "search"),
            NavItem("note_taking:images_list", "Les images", "image"),
        ),
    )
    project_usages = (ProjectUsage("note_parts__note", "note", "notes"),)
    section_usages = (SectionUsage("note_parts", "note part", "note parts"),)

    def ready(self):
        from . import dashboard, renaming

        self.dashboard_blocks = (
            DashboardBlock(
                "Note du jour",
                10,
                "note_taking/dashboard_today.html",
                dashboard.today_note,
            ),
        )

        self.section_renamer = SectionRenamer(
            occurrences=renaming.find_occurrences, rename=renaming.rename_titles
        )
