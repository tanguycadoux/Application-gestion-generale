from django.contrib import admin

from .models import Note, NotePart, NotePartImageLink


class NotePartImageLinkInline(admin.TabularInline):
    """Images utilisées par la note part (calculées à l'analyse)."""

    model = NotePartImageLink
    extra = 0
    can_delete = False
    readonly_fields = ("image",)

    def has_add_permission(self, request, obj=None):
        return False


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
        "section",
        "note__date",
        "created",
        "updated",
    )
    list_filter = (
        "note__date",
        "project",
        "section",
    )
    inlines = [NotePartImageLinkInline]
