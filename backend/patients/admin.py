from django.contrib import admin
from .models import Study

@admin.register(Study)
class StudyAdmin(admin.ModelAdmin):
    list_display = ('id', 'orthanc_path')
    search_fields = ('id', 'orthanc_path')