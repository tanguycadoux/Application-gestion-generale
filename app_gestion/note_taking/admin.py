from django.contrib import admin

from .models import Note, NotePart, Project, NotePartImage


@admin.register(Note)
class NoteAdmin(admin.ModelAdmin):
    list_display = ("pk", "date", "created", "updated", "is_test",)
    readonly_fields = ("date",)
    list_filter = ("date",)

@admin.register(NotePart)
class NotePartAdmin(admin.ModelAdmin):
    list_display = ("pk", "project", "subject", "note__date", "created", "updated",)
    list_filter = ("note__date", "project", "subject",)

@admin.register(NotePartImage)
class NotePartImageAdmin(admin.ModelAdmin):
    list_display = ("note_part", "file", "alt_text", "original_path",)

@admin.register(Project)
class ProjectAdmin(admin.ModelAdmin):
    list_display = ("pk", "name", "description",)
