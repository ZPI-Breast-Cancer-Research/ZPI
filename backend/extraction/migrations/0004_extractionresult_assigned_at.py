from django.db import migrations, models
from django.db.models import F


def backfill_assigned_at(apps, schema_editor):
    # Rows assigned before this field existed: the upload time is the best guess. The active
    # report of such a study keeps being the highest id, as before.
    ExtractionResult = apps.get_model("extraction", "ExtractionResult")
    ExtractionResult.objects.filter(study__isnull=False, assigned_at__isnull=True).update(
        assigned_at=F("created_at")
    )


class Migration(migrations.Migration):
    dependencies = [
        ("extraction", "0003_extraction_result_worker_fields"),
    ]

    operations = [
        migrations.AddField(
            model_name="extractionresult",
            name="assigned_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.RunPython(backfill_assigned_at, migrations.RunPython.noop),
    ]
