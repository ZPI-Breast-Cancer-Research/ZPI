import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    # separate from 0005: Postgres refuses to alter a table with pending deletes in one transaction
    dependencies = [
        ("patients", "0002_study_orthanc_path_unique"),
        ("segmentation", "0005_failed_status_and_timestamps"),
    ]

    operations = [
        migrations.AlterField(
            model_name="segmentationresult",
            name="study",
            field=models.OneToOneField(
                on_delete=django.db.models.deletion.CASCADE,
                related_name="segmentation",
                to="patients.study",
            ),
        ),
    ]
