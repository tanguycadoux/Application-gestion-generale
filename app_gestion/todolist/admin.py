from django.contrib import admin

from .models import Todo, Project, Tag


@admin.register(Todo)
class NoteAdmin(admin.ModelAdmin):
    list_display = ("pk", "title", "project", "description", "due_date" , "completed", "priority", "parent", "created_at", "updated_at")

@admin.register(Project)
class NoteAdmin(admin.ModelAdmin):
    list_display = ("pk", "name", "description", "created_at")
                    
@admin.register(Tag)
class NoteAdmin(admin.ModelAdmin):
    list_display = ("pk", "name")
