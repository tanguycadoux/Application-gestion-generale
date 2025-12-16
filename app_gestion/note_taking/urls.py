from django.urls import path

from . import views


app_name = "note_taking"

urlpatterns = [
    path("", views.index, name="index"),
    path("notes/", views.notes_list, name="notes_list"),
    path("notes/<str:date>/md/", views.note_md, name="note_md"),
    path("notes/<str:date>/json/", views.note_json, name="note_json"),
    path("notes/import/", views.import_note, name="import_note"),
    path("notes/overwrite/", views.overwrite_notes, name="overwrite_notes"),
    path("notes/synchronize_all/", views.synchronize_notes, name="synchronize_notes"),
]
