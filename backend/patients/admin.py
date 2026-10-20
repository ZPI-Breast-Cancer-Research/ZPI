from django.contrib import admin
from extraction.models import ExtractionRun
from segmentation.models import SegmentationRun
from .models import Patient, Study, Image

class ImageInline(admin.TabularInline):
    model = Image
    extra = 0
    readonly_fields = ("created_at",)

class ExtractionRunInline(admin.TabularInline):
    model = ExtractionRun
    extra = 0
    readonly_fields = ("result_predicted", "created_at", "accepted_at")

class SegmentationRunInline(admin.TabularInline):
    model = SegmentationRun
    extra = 0
    readonly_fields = ("mask_path_predicted", "created_at", "accepted_at")

@admin.register(Patient)
class PatientAdmin(admin.ModelAdmin):
    list_display = ("id", "age")
    search_fields = ("id",)
    list_filter = ("age",)

@admin.register(Study)
class StudyAdmin(admin.ModelAdmin):
    list_display = ("id", "patient", "study_date", "created_at")
    list_filter = ("study_date", "created_at")
    search_fields = ("id", "patient__id")
    readonly_fields = ("created_at",)
    inlines = [ImageInline, ExtractionRunInline]

@admin.register(Image)
class ImageAdmin(admin.ModelAdmin):
    list_display = ("id", "study", "modality", "image_path", "created_at")
    list_filter = ("modality", "created_at")
    search_fields = ("id", "study__id", "image_path")
    readonly_fields = ("created_at",)
    inlines = [SegmentationRunInline]
