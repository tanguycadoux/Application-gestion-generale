from django.contrib import admin

from .models import Image


@admin.register(Image)
class ImageAdmin(admin.ModelAdmin):
    list_display = ("pk", "name", "file", "created_at")
    search_fields = ("name",)
