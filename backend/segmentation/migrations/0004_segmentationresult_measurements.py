from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("segmentation", "0003_seg_uids"),
    ]

    operations = [
        migrations.AddField(
            model_name="segmentationresult",
            name="measurements",
            field=models.JSONField(blank=True, null=True),
        ),
    ]
