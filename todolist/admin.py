from django.contrib import admin

from .models import Tag, Todo


@admin.register(Todo)
class TodoAdmin(admin.ModelAdmin):
    list_display = (
        "pk",
        "title",
        "project",
        "description",
        "due_date",
        "completed",
        "priority",
        "parent",
        "created_at",
        "updated_at",
        "created_from_note",
    )
    list_filter = ("created_from_note",)


@admin.register(Tag)
class TagAdmin(admin.ModelAdmin):
    list_display = ("pk", "name")
