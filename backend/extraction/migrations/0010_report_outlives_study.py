import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("extraction", "0009_report_source"),
        ("patients", "0002_study_orthanc_path_unique"),
    ]

    operations = [
        migrations.AlterField(
            model_name="extractionresult",
            name="study",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="extractions",
                to="patients.study",
            ),
        ),
    ]
