from django.conf import settings
from django.db import models

from mlops.models import ModelVersion, ReviewStatus
from patients.models import Image


class SegmentationRun(models.Model):
    image = models.ForeignKey(Image, on_delete=models.CASCADE, related_name="segmentation_runs")
    model = models.ForeignKey(ModelVersion, on_delete=models.PROTECT, related_name="+")
    mask_path_predicted = models.CharField(max_length=500)
    mask_path_accepted = models.CharField(max_length=500, blank=True)
    status = models.CharField(
        max_length=20, choices=ReviewStatus.choices, default=ReviewStatus.PENDING, db_index=True
    )
    accepted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="accepted_segmentations",
    )
    accepted_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
