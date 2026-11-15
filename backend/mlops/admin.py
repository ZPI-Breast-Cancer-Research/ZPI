from django.contrib import admin

from .models import ModelVersion, ModuleUsagePeriod


class ModuleUsagePeriodInline(admin.TabularInline):
    model = ModuleUsagePeriod
    extra = 0
    autocomplete_fields = ("decided_by",)


@admin.register(ModelVersion)
class ModelVersionAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "name",
        "version",
        "module",
        "status",
        "dataset",
        "proposed_at",
        "created_at",
    )
    list_filter = (
        "module",
        "status",
    )
    search_fields = (
        "name",
        "version",
        "mlflow_run_id",
    )
    readonly_fields = ("created_at",)
    autocomplete_fields = ("proposed_by", "decided_by")
    inlines = (ModuleUsagePeriodInline,)
