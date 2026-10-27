from django.urls import path

from core import converters  # noqa: F401  (le convertisseur `date`)

from . import views

app_name = "note_taking"

# Une note s'adresse par sa date (#273) ; l'adresse par id redirige.
urlpatterns = [
    path("notes/", views.index, name="index"),
    path("notes/list/", views.NoteList.as_view(), name="notes_list"),
    path("notes/search/", views.notes_search, name="notes_search"),
    path("notes/search/paths/", views.get_subjects, name="get_subjects"),
    path("notes/export/", views.export_notes, name="export_notes"),
    path("notes/import/", views.import_files, name="import_files"),
    path("notes/new/", views.new_note, name="new_note"),
    path("notes/today/", views.note_today, name="note_today"),
    path("notes/<date:note_date>/", views.NoteDetail.as_view(), name="note_detail"),
    path("notes/<date:note_date>/md/", views.note_md, name="note_md"),
    path("notes/<date:note_date>/json/", views.note_json, name="note_json"),
    path("notes/<date:note_date>/export/", views.export_note, name="export_note"),
    path("notes/<date:note_date>/edit/", views.edit_note, name="edit_note"),
    path("notes/<date:note_date>/delete/", views.delete_note, name="delete_note"),
    path(
        "notes/<date:note_date>/source/",
        views.update_source_file,
        name="update_source_file",
    ),
    path("notes/<int:pk>/", views.note_by_id, name="note_by_id"),
    path("notes/<int:pk>/<slug:action>/", views.note_by_id, name="note_by_id_action"),
    path("note_taking/note/<int:pk>/", views.note_by_id),
    path("note_taking/note/<int:pk>/<slug:action>/", views.note_by_id),
    path("images/", views.ImageList.as_view(), name="images_list"),
    path("images/capture/", views.image_capture, name="image_capture"),
    path("images/suggestions/", views.image_suggestions, name="image_suggestions"),
    path("images/<int:pk>/", views.ImageDetail.as_view(), name="image_detail"),
    path("images/<int:pk>/delete/", views.delete_image, name="delete_image"),
]
