from django.contrib import admin

from .models import Note, NotePart


@admin.register(Note)
class NoteAdmin(admin.ModelAdmin):
    list_display = ("pk", "date", "created", "updated", "is_test",)
    readonly_fields = ("date",)
    list_filter = ("date",)

admin.site.register(NotePart)