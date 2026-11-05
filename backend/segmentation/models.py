from django.db import models


class StatusChoices(models.TextChoices):
    PENDING = 'PENDING', 'Oczekujący'
    PROCESSING = 'PROCESSING', 'Przetwarzany'
    COMPLETED = 'COMPLETED', 'Ukończony'
    APPROVED = 'APPROVED', 'Zatwierdzony'
    CORRECTED = 'CORRECTED', 'Poprawiony'
    REJECTED = 'REJECTED', 'Odrzucony'

class SegmentationResult(models.Model):
    study = models.ForeignKey(
        'patients.Study', 
        on_delete=models.CASCADE, 
        related_name='segmentations'
    )
    model = models.ForeignKey(
        'mlops.ModelVersion', 
        on_delete=models.SET_NULL, 
        null=True, 
        related_name='segmentation_results'
    )
    status = models.CharField(
        max_length=20, 
        choices=StatusChoices.choices, 
        default=StatusChoices.PENDING
    )
    uncertainity = models.FloatField(blank=True, null=True)
    generated_path = models.CharField(max_length=500, blank=True, null=True)
    accepted_path = models.CharField(max_length=500, blank=True, null=True)
    input_series_ids = models.JSONField(default=list, blank=True, help_text="List ID series from Orthanca used as input")
    accepted_by = models.ForeignKey(
        'users.User', 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True, 
        related_name='accepted_segmentations'
    )
    accepted_at = models.DateField(blank=True, null=True)

    class Meta:
        db_table = 'segmentation_results'

    def __str__(self):
        return f"Segmentation #{self.id} (Study: {self.study_id}) [Status: {self.status}]"