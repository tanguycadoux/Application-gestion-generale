from django.urls import path

from . import converters, views  # noqa: F401  (le convertisseur `date`)

app_name = "core"

urlpatterns = [
    path("", views.index, name="index"),
    path("projects/", views.projects, name="projects"),
    path("projects/new/", views.ProjectCreateView.as_view(), name="project_create"),
    path(
        "projects/suggestions/", views.project_suggestions, name="project_suggestions"
    ),
    path(
        "projects/<int:pk>/edit/",
        views.ProjectEditView.as_view(),
        name="project_edit",
    ),
    path("projects/<int:pk>/delete/", views.delete_project, name="project_delete"),
    path("projects/<int:pk>/paths/", views.project_paths, name="project_paths"),
    path(
        "projects/<int:pk>/paths/<int:section_pk>/rename/",
        views.rename_section,
        name="section_rename",
    ),
    path(
        "projects/<int:pk>/paths/<int:section_pk>/delete/",
        views.delete_section,
        name="section_delete",
    ),
    path("paths/suggestions/", views.section_suggestions, name="section_suggestions"),
]
