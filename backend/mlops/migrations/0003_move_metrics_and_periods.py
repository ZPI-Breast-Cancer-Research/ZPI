from django.db import migrations

METRICS = ("dice", "hd95", "f1")
GATE_REASON = "Odrzucona przez bramkę jakości"


def forwards(apps, schema_editor):
    ModelVersion = apps.get_model("mlops", "ModelVersion")
    Period = apps.get_model("mlops", "ModuleUsagePeriod")
    for version in ModelVersion.objects.all():
        version.metrics = {
            key: getattr(version, key) for key in METRICS if getattr(version, key) is not None
        }
        # a candidate was shown as proposed only while its decision was pending
        if version.status == "candidate" and version.decision != "pending":
            version.status = "new"
        if version.status == "rejected" and version.decision == "rejected_gate" and not version.reason:
            version.reason = GATE_REASON
        version.save()

        in_use = version.status == "production"
        started = version.activated_at or (version.created_at if in_use else None)
        if started:
            Period.objects.create(
                module_version=version,
                started_at=started,
                ended_at=None if in_use else version.deactivated_at or started,
                decided_by=version.decided_by,
            )


def backwards(apps, schema_editor):
    ModelVersion = apps.get_model("mlops", "ModelVersion")
    Period = apps.get_model("mlops", "ModuleUsagePeriod")
    decisions = {"production": "promoted", "archived": "replaced", "rejected": "rejected", "new": "baseline"}
    for version in ModelVersion.objects.all():
        for key in METRICS:
            setattr(version, key, version.metrics.get(key))
        last = Period.objects.filter(module_version=version).order_by("-started_at").first()
        version.activated_at = last.started_at if last else None
        version.deactivated_at = last.ended_at if last else None
        if version.status == "rejected" and version.reason == GATE_REASON:
            version.decision = "rejected_gate"
        else:
            version.decision = decisions.get(version.status, "pending")
        if version.status == "new":
            version.status = "candidate"
        version.save()


class Migration(migrations.Migration):

    dependencies = [
        ('mlops', '0002_module_version'),
    ]

    operations = [
        migrations.RunPython(forwards, backwards),
    ]
