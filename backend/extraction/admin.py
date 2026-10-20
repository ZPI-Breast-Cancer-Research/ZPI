from django.contrib import admin
from .models import ExtractionRun

@admin.register(ExtractionRun)
class ExtractionRunAdmin(admin.ModelAdmin):
    list_display = ("id", "study", "model", "status", "accepted_by", "created_at")
    list_filter = ("status", "created_at", "model")
    search_fields = ("id", "study__id")
    readonly_fields = ("result_predicted", "result_accepted", "created_at", "accepted_at")
