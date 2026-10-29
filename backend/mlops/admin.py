from django.contrib import admin
from .models import ModelVersion


@admin.register(ModelVersion)
class ModelVersionAdmin(admin.ModelAdmin):
    list_display = (
        'id', 
        'name', 
        'version', 
        'module', 
        'status', 
        'decision', 
        'dice', 
        'f1', 
        'activated_at'
    )
    list_filter = (
        'module', 
        'status', 
        'decision',
    )
    search_fields = (
        'name', 
        'version', 
        'mlflow_run_id',
    )
    readonly_fields = ('created_at',)
    autocomplete_fields = ('decided_by',)