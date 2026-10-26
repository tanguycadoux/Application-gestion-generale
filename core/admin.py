from django.contrib import admin

from .models import Project, Section, Tag


@admin.register(Project)
class ProjectAdmin(admin.ModelAdmin):
    list_display = ("pk", "name", "description", "created_at")
    search_fields = ("name",)


@admin.register(Section)
class SectionAdmin(admin.ModelAdmin):
    list_display = ("pk", "project", "__str__")
    list_filter = ("project",)
    search_fields = ("name",)


@admin.register(Tag)
class TagAdmin(admin.ModelAdmin):
    list_display = ("pk", "name")
    search_fields = ("name",)
