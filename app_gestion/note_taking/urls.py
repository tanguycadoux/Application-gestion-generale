from django.urls import path

from . import views


app_name = "note_taking"

urlpatterns = [
    path("", views.index, name="index"),
    path("notes/", views.NoteList.as_view(), name="notes_list"),

    path("note/<int:pk>/", views.NoteDetail.as_view(), name="note_detail"),
    path("note/<int:pk>/md/", views.note_md, name="note_md"),
    path("note/<int:pk>/json/", views.note_json, name="note_json"),

    path("note/import/", views.import_note, name="import_note"),

    path("projects/", views.ProjectList.as_view(), name="projects_list"),

    path("project/<int:pk>/", views.ProjectDetail.as_view(), name="project_detail"),

    # ADMIN
    path("notes/clear/", views.clear_notes, name="clear_notes"),
]
