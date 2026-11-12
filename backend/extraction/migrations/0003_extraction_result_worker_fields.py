import django.utils.timezone
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("extraction", "0002_initial"),
    ]

    operations = [
        migrations.AlterField(
            model_name="extractionresult",
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
        migrations.AddField(
            model_name="extractionresult",
            name="error",
            field=models.TextField(
                blank=True, default="", help_text="Why the extraction failed (status FAILED)"
            ),
        ),
        migrations.AddField(
            model_name="extractionresult",
            name="warnings",
            field=models.JSONField(
                blank=True,
                default=list,
                help_text="Fields that do not follow from the report text",
            ),
        ),
        migrations.AddField(
            model_name="extractionresult",
            name="provenance",
            field=models.JSONField(
                blank=True,
                help_text="LLM model, prompt, schema and OCR that produced the result",
                null=True,
            ),
        ),
        # Existing rows get the migration time; new rows get their creation time.
        migrations.AddField(
            model_name="extractionresult",
            name="created_at",
            field=models.DateTimeField(auto_now_add=True, default=django.utils.timezone.now),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name="extractionresult",
            name="updated_at",
            field=models.DateTimeField(auto_now=True),
        ),
    ]
