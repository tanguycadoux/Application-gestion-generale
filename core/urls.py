from django.urls import path

from . import views

app_name = "core"

urlpatterns = [
    path("", views.index, name="index"),
    path("projets/", views.projects, name="projects"),
    path("projets/nouveau/", views.ProjectCreateView.as_view(), name="project_create"),
    path(
        "projets/<int:pk>/modifier/",
        views.ProjectEditView.as_view(),
        name="project_edit",
    ),
    path("projets/<int:pk>/chemins/", views.project_paths, name="project_paths"),
    path(
        "projets/<int:pk>/chemins/<int:section_pk>/renommer/",
        views.rename_section,
        name="section_rename",
    ),
    path(
        "projets/<int:pk>/chemins/<int:section_pk>/supprimer/",
        views.delete_section,
        name="section_delete",
    ),
    path(
        "projets/<int:pk>/supprimer/",
        views.delete_project,
        name="project_delete",
    ),
]
