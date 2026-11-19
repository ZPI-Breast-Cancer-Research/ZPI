import django.utils.timezone
from django.db import migrations, models

VERIFIED = ("APPROVED", "CORRECTED")


def forwards(apps, schema_editor):
    """Prepare the data for one result per study (0006).

    A failed run used to be saved as REJECTED without a mask; it becomes FAILED. Of several
    results of one study the verified one stays, otherwise the newest; the other rows go (their
    files stay in storage).
    """
    Result = apps.get_model("segmentation", "SegmentationResult")
    Result.objects.filter(status="REJECTED", generated_path__isnull=True).update(
        status="FAILED", error="Segmentation failed (recorded before the FAILED status existed)"
    )
    Result.objects.filter(status="REJECTED", generated_path="").update(
        status="FAILED", error="Segmentation failed (recorded before the FAILED status existed)"
    )

    keep: dict[int, object] = {}
    for result in Result.objects.order_by("study_id", "id"):
        kept = keep.get(result.study_id)
        if kept is None or result.status in VERIFIED or kept.status not in VERIFIED:
            keep[result.study_id] = result
    Result.objects.exclude(id__in=[r.id for r in keep.values()]).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("segmentation", "0004_segmentationresult_measurements"),
    ]

    operations = [
        migrations.AddField(
            model_name="segmentationresult",
            name="error",
            field=models.TextField(
                blank=True, default="", help_text="Why the segmentation failed"
            ),
        ),
        migrations.AddField(
            model_name="segmentationresult",
            name="created_at",
            field=models.DateTimeField(auto_now_add=True, default=django.utils.timezone.now),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name="segmentationresult",
            name="updated_at",
            field=models.DateTimeField(auto_now=True),
        ),
        migrations.AlterField(
            model_name="segmentationresult",
            name="status",
            field=models.CharField(
                choices=[
                    ("PENDING", "Oczekujący"),
                    ("PROCESSING", "Przetwarzany"),
                    ("COMPLETED", "Ukończony"),
                    ("APPROVED", "Zatwierdzony"),
                    ("CORRECTED", "Poprawiony"),
                    ("REJECTED", "Odrzucony"),
                    ("FAILED", "Błąd"),
                ],
                default="PENDING",
                max_length=20,
            ),
        ),
        migrations.RunPython(forwards, migrations.RunPython.noop),
    ]
