from django.contrib import admin
from .models import SegmentationRun

@admin.register(SegmentationRun)
class SegmentationRunAdmin(admin.ModelAdmin):
    list_display = ("id", "image", "model", "status", "accepted_by", "created_at")
    list_filter = ("status", "created_at", "model")
    search_fields = ("id", "image__id")
    readonly_fields = ("mask_path_predicted", "mask_path_accepted", "created_at", "accepted_at")
