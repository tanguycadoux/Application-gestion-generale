from django.apps import AppConfig

from core.app_registry import (
    DashboardBlock,
    NavItem,
    NavSection,
    ProjectRenamer,
    ProjectUsage,
    SectionRenamer,
    SectionUsage,
    WeekBlock,
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
    search_page = NavItem(
        "note_taking:notes_search", "Rechercher dans les notes", "search"
    )
    # Capture rapide dans la note du jour (#386).
    header_templates = ("note_taking/quick_capture.html",)
    project_usages = (ProjectUsage("passages__note", "note", "notes"),)
    # Un niveau compte ses passages (#362, #387).
    section_usages = (
        SectionUsage(
            "passages",
            "passage",
            "passages",
            url_name="note_taking:notes_search",
            query="subjects={pk}",
        ),
    )

    debug_pages = (NavItem("note_taking:debug_note_json", "Analyse JSON", "toc"),)

    def ready(self):
        from . import dashboard, renaming, search_index, week  # noqa: F401 (récepteurs)

        self.dashboard_blocks = (
            DashboardBlock(
                "Note du jour",
                10,
                "note_taking/dashboard_today.html",
                dashboard.today_note,
            ),
        )

        self.week_blocks = (
            WeekBlock("Notes", 10, "note_taking/week_notes.html", week.week_notes),
        )

        self.section_renamer = SectionRenamer(
            occurrences=renaming.find_occurrences, rename=renaming.rename_titles
        )
        self.project_renamer = ProjectRenamer(
            occurrences=renaming.project_occurrences,
            rename=renaming.rename_project_titles,
        )
