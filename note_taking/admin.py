from django.contrib import admin

from .models import Note, Passage, PassageImageLink


class PassageImageLinkInline(admin.TabularInline):
    """Images utilisées par le passage (calculées à l'analyse)."""

    model = PassageImageLink
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

    def save_model(self, request, obj, form, change):
        obj.save(source=Note.Source.ADMIN)


@admin.register(Passage)
class PassageAdmin(admin.ModelAdmin):
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
    inlines = [PassageImageLinkInline]
