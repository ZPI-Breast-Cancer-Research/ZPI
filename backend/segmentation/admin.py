from django.contrib import admin
from .models import SegmentationResult


@admin.register(SegmentationResult)
class SegmentationResultAdmin(admin.ModelAdmin):
    list_display = (
        'id', 
        'study', 
        'model', 
        'status', 
        'accepted_by', 
        'accepted_at'
    )
    list_filter = (
        'status', 
        'model__module', 
    )
    search_fields = (
        'study__id', 
        'generated_path', 
    )
    autocomplete_fields = ('study', 'model', 'accepted_by')
    readonly_fields = ('id',)