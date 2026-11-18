from django.db import migrations


class Migration(migrations.Migration):
    # separate from 0012: the data is copied into the columns first
    dependencies = [
        ("extraction", "0012_report_columns"),
    ]

    operations = [
        migrations.RemoveField(model_name="extractionresult", name="provenance"),
        migrations.RemoveField(model_name="extractionresult", name="result"),
    ]
