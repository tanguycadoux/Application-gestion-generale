from django.contrib import admin

from .models import Image


@admin.register(Image)
class ImageAdmin(admin.ModelAdmin):
    list_display = ("pk", "name", "kind", "file", "created_at")
    list_filter = ("kind",)
    search_fields = ("name",)
