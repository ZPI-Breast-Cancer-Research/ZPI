from django.contrib import admin
from .models import ExtractionResult

@admin.register(ExtractionResult)
class ExtractionResultAdmin(admin.ModelAdmin):
    list_display = ('id', 'study', 'status', 'accepted_at')
    list_filter = ('status',)