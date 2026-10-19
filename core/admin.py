from django.contrib import admin

from .models import Project, Subject, Tag


@admin.register(Project)
class ProjectAdmin(admin.ModelAdmin):
    list_display = ("pk", "name", "description", "created_at")
    search_fields = ("name",)


@admin.register(Subject)
class SubjectAdmin(admin.ModelAdmin):
    list_display = ("pk", "name")
    search_fields = ("name",)


@admin.register(Tag)
class TagAdmin(admin.ModelAdmin):
    list_display = ("pk", "name")
    search_fields = ("name",)
