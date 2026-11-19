from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("extraction", "0005_extractionresult_result"),
    ]

    operations = [
        migrations.AddField(
            model_name="extractionresult",
            name="lesion_answers",
            field=models.JSONField(
                blank=True,
                help_text="Confirmed or corrected fields per lesion, from the review form",
                null=True,
            ),
        ),
    ]
