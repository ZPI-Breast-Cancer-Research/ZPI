from django.db import models


class ModelVersion(models.Model):

    class ModuleChoices(models.TextChoices):
        SEG = "seg", "SEG"
        EXT = "ext", "EXT"

    class StatusChoices(models.TextChoices):
        CANDIDATE = "candidate", "Candidate"
        PRODUCTION = "production", "Production"
        ARCHIVED = "archived", "Archived"
        REJECTED = "rejected", "Rejected"
        TRAINING = "training", "Training"

    class DecisionChoices(models.TextChoices):
        PROMOTED = "promoted", "Promoted"
        REPLACED = "replaced", "Replaced"
        REJECTED_GATE = "rejected_gate", "Rejected Gate"
        REJECTED = "rejected", "Rejected"
        PENDING = "pending", "Pending"
        BASELINE = "baseline", "Baseline"

    module = models.CharField(
        max_length=3,
        choices=ModuleChoices.choices,
        default=ModuleChoices.SEG,
    )
    name = models.CharField(max_length=100)
    version = models.CharField(max_length=50)
    
    status = models.CharField(
        max_length=20,
        choices=StatusChoices.choices,
        default=StatusChoices.CANDIDATE,
    )
    decision = models.CharField(
        max_length=20,
        choices=DecisionChoices.choices,
        default=DecisionChoices.PENDING,
    )
    
    activated_at = models.DateTimeField(null=True, blank=True)
    deactivated_at = models.DateTimeField(null=True, blank=True)
    decided_by = models.ForeignKey("users.User", null=True, blank=True, on_delete=models.SET_NULL)
    mlflow_run_id = models.CharField(max_length=64, blank=True)
    dice = models.FloatField(null=True, blank=True)
    hd95 = models.FloatField(null=True, blank=True)
    f1 = models.FloatField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["module", "version"], name="uniq_module_version"),
        ]

    def __str__(self):
        return f"{self.module} v{self.version}"