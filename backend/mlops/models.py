from django.db import models


class ReviewStatus(models.TextChoices):
    PENDING = "pending", "Oczekuje"
    APPROVED = "approved", "Zatwierdzone"
    CORRECTED = "corrected", "Poprawione"


class ModelVersion(models.Model):
    class ModelType(models.TextChoices):
        SEGMENTATION = "segmentation", "Segmentacja"
        EXTRACTION = "extraction", "Ekstrakcja"

    name = models.CharField(max_length=100)
    type = models.CharField(max_length=20, choices=ModelType.choices)
    version = models.CharField(max_length=50)
    path = models.CharField(max_length=500, blank=True)
    metrics = models.JSONField(null=True, blank=True)
    trained_date = models.DateField(null=True, blank=True)
    train_config = models.JSONField(null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["name", "version"], name="uniq_model_name_version")
        ]
