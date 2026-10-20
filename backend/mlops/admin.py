from django.contrib import admin
from .models import ModelVersion

@admin.register(ModelVersion)
class ModelVersionAdmin(admin.ModelAdmin):
    list_display = ("id", "name", "version", "type", "trained_date")
    list_filter = ("type", "trained_date")
    search_fields = ("name", "version")
    readonly_fields = ("trained_date", "metrics", "train_config")
