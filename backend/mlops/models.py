from django.db import models, transaction
from django.utils import timezone


class ModelVersion(models.Model):
    """A version of one processing module: segmentation model, OCR, or report extraction."""

    class ModuleChoices(models.TextChoices):
        SEG = "seg", "SEG"
        EXT = "ext", "EXT"
        OCR = "ocr", "OCR"

    class StatusChoices(models.TextChoices):
        NEW = "new", "New"  # a draft: can still be edited, not proposed yet
        TRAINING = "training", "Training"
        CANDIDATE = "candidate", "Candidate"  # proposed, waits for a decision
        PRODUCTION = "production", "Production"
        ARCHIVED = "archived", "Archived"
        REJECTED = "rejected", "Rejected"

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
        default=StatusChoices.NEW,
    )

    proposed_by = models.ForeignKey(
        "users.User",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="proposed_versions",
    )
    proposed_at = models.DateTimeField(null=True, blank=True)
    reason = models.TextField(
        blank=True, default="", help_text="Reason of the proposal or the decision"
    )
    restore = models.BooleanField(
        default=False, help_text="The proposal brings back an archived version"
    )
    decided_by = models.ForeignKey("users.User", null=True, blank=True, on_delete=models.SET_NULL)

    trained_at = models.DateTimeField(null=True, blank=True)
    training_cases = models.PositiveIntegerField(null=True, blank=True)
    celery_task_id = models.CharField(max_length=64, blank=True, default="")

    dataset = models.CharField(
        max_length=100,
        blank=True,
        default="",
        help_text=(
            "Set the version was trained on and its metrics were computed on; written by the worker"
        ),
    )
    # Keys depend on the module, e.g. seg: dice, iou, hd95, dice_small, volume_error_pct; ext: f1.
    metrics = models.JSONField(default=dict, blank=True)
    metrics_cases = models.PositiveIntegerField(null=True, blank=True)
    mlflow_run_id = models.CharField(max_length=64, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        # not "model_versions": MLflow keeps its own table of that name in the same database
        db_table = "module_version"
        constraints = [
            models.UniqueConstraint(fields=["module", "version"], name="uniq_module_version"),
        ]

    def __str__(self):
        return f"{self.module} v{self.version}"

    @property
    def editable(self) -> bool:
        """Only a draft can change; from the proposal on a version stays as it is."""
        return self.status == self.StatusChoices.NEW

    def put_in_use(self, user, reason: str = "") -> None:
        """Make this the version in use of its module and retire the one it replaces.

        The status and the usage periods change together, so they cannot disagree.
        """
        now = timezone.now()
        with transaction.atomic():
            replaced = ModelVersion.objects.filter(
                module=self.module, status=self.StatusChoices.PRODUCTION
            ).exclude(pk=self.pk)
            ModuleUsagePeriod.objects.filter(
                module_version__in=replaced, ended_at__isnull=True
            ).update(ended_at=now)
            replaced.update(status=self.StatusChoices.ARCHIVED)

            self.status = self.StatusChoices.PRODUCTION
            self.decided_by = user
            self.reason = reason
            self.save()
            if not self.periods.filter(ended_at__isnull=True).exists():
                self.periods.create(started_at=now, decided_by=user)


class ModuleUsagePeriod(models.Model):
    """When a version was in use. A restored version has more than one period."""

    module_version = models.ForeignKey(
        ModelVersion, on_delete=models.CASCADE, related_name="periods"
    )
    started_at = models.DateTimeField()
    ended_at = models.DateTimeField(
        null=True, blank=True, help_text="Empty while the version is in use"
    )
    decided_by = models.ForeignKey("users.User", null=True, blank=True, on_delete=models.SET_NULL)

    class Meta:
        db_table = "module_usage_period"
        ordering = ["started_at"]

    def __str__(self):
        return (
            f"{self.module_version} {self.started_at:%Y-%m-%d} – {self.ended_at:%Y-%m-%d}"
            if self.ended_at
            else f"{self.module_version} since {self.started_at:%Y-%m-%d}"
        )
