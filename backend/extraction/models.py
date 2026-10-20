from django.conf import settings
from django.db import models

from mlops.models import ModelVersion, ReviewStatus
from patients.models import Study


class ExtractionRun(models.Model):
    study = models.ForeignKey(Study, on_delete=models.CASCADE, related_name="extraction_runs")
    model = models.ForeignKey(ModelVersion, on_delete=models.PROTECT, related_name="+")
    result_predicted = models.JSONField()
    result_accepted = models.JSONField(null=True, blank=True)
    status = models.CharField(
        max_length=20, choices=ReviewStatus.choices, default=ReviewStatus.PENDING, db_index=True
    )
    accepted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="accepted_extractions",
    )
    accepted_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
