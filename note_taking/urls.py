from django.urls import path

from . import views

app_name = "note_taking"

urlpatterns = [
    path("", views.index, name="index"),
    path("notes/", views.NoteList.as_view(), name="notes_list"),
    path("notes/search/", views.notes_search, name="notes_search"),
    path("notes/export/", views.export_notes, name="export_notes"),
    path("notes/import/", views.import_files, name="import_files"),
    path("get-subjects/", views.get_subjects, name="get_subjects"),
    path("note/new/", views.new_note, name="new_note"),
    path("note/today/", views.note_today, name="note_today"),
    path(
        "note/update_source_file/<int:pk>",
        views.update_source_file,
        name="update_source_file",
    ),
    path("note/<int:pk>/", views.NoteDetail.as_view(), name="note_detail"),
    path("note/<int:pk>/md/", views.note_md, name="note_md"),
    path("note/<int:pk>/json/", views.note_json, name="note_json"),
    path("note/<int:pk>/export/", views.export_note, name="export_note"),
    path("note/<int:pk>/edit/", views.edit_note, name="edit_note"),
    path("note/<int:pk>/delete/", views.delete_note, name="delete_note"),
    path("images/", views.ImageList.as_view(), name="images_list"),
    path("images/suggestions/", views.image_suggestions, name="image_suggestions"),
    path("images/<int:pk>/", views.ImageDetail.as_view(), name="image_detail"),
    path("images/<int:pk>/delete/", views.delete_image, name="delete_image"),
]
