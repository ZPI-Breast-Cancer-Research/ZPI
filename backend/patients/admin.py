from django.contrib import admin
from extraction.models import ExtractionResult
from segmentation.models import SegmentationResult

from .models import Study


class SegmentationResultInline(admin.TabularInline):
    model = SegmentationResult
    extra = 0
    readonly_fields = ("status", "generated_path")


class ExtractionResultInline(admin.TabularInline):
    model = ExtractionResult
    extra = 0
    readonly_fields = ("status", "generated_report")


@admin.register(Study)
class StudyAdmin(admin.ModelAdmin):
    list_display = ("id", "orthanc_path")
    search_fields = ("id", "orthanc_path")
    inlines = [SegmentationResultInline, ExtractionResultInline]
