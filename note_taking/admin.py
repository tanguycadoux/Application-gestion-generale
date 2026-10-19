from django.contrib import admin

from .models import Note, NotePart, NotePartImage


@admin.register(Note)
class NoteAdmin(admin.ModelAdmin):
    list_display = (
        "pk",
        "date",
        "created",
        "updated",
    )
    readonly_fields = ("date",)
    list_filter = ("date",)


@admin.register(NotePart)
class NotePartAdmin(admin.ModelAdmin):
    list_display = (
        "pk",
        "project",
        "subject",
        "note__date",
        "created",
        "updated",
    )
    list_filter = (
        "note__date",
        "project",
        "subject",
    )


@admin.register(NotePartImage)
class NotePartImageAdmin(admin.ModelAdmin):
    list_display = (
        "pk",
        "file",
        "original_path",
    )
