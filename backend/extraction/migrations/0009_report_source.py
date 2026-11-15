from django.db import migrations

IMAGE_SUFFIXES = (".jpg", ".jpeg", ".png")


def forwards(apps, schema_editor):
    """Rows from before `source` existed: an image was read by OCR, any other file is text.

    A row without a file keeps the default; forms filled in by hand did not exist yet.
    """
    Report = apps.get_model("extraction", "ExtractionResult")
    for report in Report.objects.exclude(report_path__isnull=True).exclude(report_path=""):
        is_image = report.report_path.lower().endswith(IMAGE_SUFFIXES)
        report.source = "scan" if is_image else "text"
        report.save(update_fields=["source"])


class Migration(migrations.Migration):

    dependencies = [
        ('extraction', '0008_reports_table'),
    ]

    operations = [
        migrations.RunPython(forwards, migrations.RunPython.noop),
    ]
