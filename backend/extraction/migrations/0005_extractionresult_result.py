from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("extraction", "0004_extractionresult_assigned_at"),
    ]

    operations = [
        migrations.AddField(
            model_name="extractionresult",
            name="result",
            field=models.JSONField(
                blank=True,
                help_text=(
                    "Full ExtractionResult of the worker (workers/extraction/schema.py): data, "
                    "OCR text, warnings, provenance; what the frontend shows as the report"
                ),
                null=True,
            ),
        ),
    ]
