from datetime import timedelta

from django.conf import settings
from django.db.models import Count, Q
from django.db.models.functions import TruncWeek
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from celery import current_app

from extraction.models import ExtractionResult, StatusChoices as ExtStatus
from review.views import REPORT_FIELDS, _as_fields
from segmentation.models import SegmentationResult, StatusChoices as SegStatus
from users.permissions import require_permission
from audit.utils import record_audit
from .models import ModelVersion

VERIFIED = (SegStatus.APPROVED, SegStatus.CORRECTED)
# retraining starts when enough corrections have piled up; override in settings.py
RETRAIN_THRESHOLD = getattr(settings, "RETRAIN_THRESHOLD", 50)
RETRAIN_HOUR = getattr(settings, "RETRAIN_HOUR", 2)
WEEKS = 8

FIELD_LABELS = {
    "birads": "BI-RADS",
    "location": "Lokalizacja",
    "size": "Wymiar",
    "shape": "Kształt",
    "margin": "Brzegi",
    "curve": "Krzywa",
}


def _iso(value):
    return value.strftime("%Y-%m-%d") if value else None


def _full_name(user):
    if not user:
        return None
    return f"{user.first_name} {user.last_name}".strip() or user.username


def _corrected_share(queryset):
    """Share of CORRECTED among verified segmentations, None when nothing is verified yet."""
    agg = queryset.filter(status__in=VERIFIED).aggregate(
        total=Count("id"), corrected=Count("id", filter=Q(status=SegStatus.CORRECTED))
    )
    return round(agg["corrected"] / agg["total"], 2) if agg["total"] else None


def _weekly_corrected(db_versions):
    since = timezone.localdate() - timedelta(weeks=WEEKS)
    rows = (
        SegmentationResult.objects.filter(status__in=VERIFIED, accepted_at__gte=since)
        .annotate(week=TruncWeek("accepted_at"))
        .values("week")
        .annotate(total=Count("id"), corrected=Count("id", filter=Q(status=SegStatus.CORRECTED)))
        .order_by("week")
    )

    # the week in which a version went to production, so the chart can mark it
    activations = {}
    for m in db_versions.filter(activated_at__isnull=False, activated_at__date__gte=since):
        day = timezone.localtime(m.activated_at).date()
        activations[day - timedelta(days=day.weekday())] = str(m.version)

    result = []
    for row in rows:
        item = {"week": _iso(row["week"]), "share": round(row["corrected"] / row["total"], 2)}
        if row["week"] in activations:
            item["versionChange"] = activations[row["week"]]
        result.append(item)
    return result


def _next_retraining(db_versions):
    """Corrections collected since the newest version was created, and the next nightly window."""
    corrections = SegmentationResult.objects.filter(status=SegStatus.CORRECTED)
    newest = db_versions.first()
    if newest:
        corrections = corrections.filter(accepted_at__gte=timezone.localtime(newest.created_at).date())

    now = timezone.localtime()
    window = now.replace(hour=RETRAIN_HOUR, minute=0, second=0, microsecond=0)
    if window <= now:
        window += timedelta(days=1)

    return {
        "corrections": corrections.count(),
        "threshold": RETRAIN_THRESHOLD,
        "window": window.strftime("%Y-%m-%dT%H:%M"),
    }


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def segmentation_overview(request):
    db_versions = (
        ModelVersion.objects.filter(module=ModelVersion.ModuleChoices.SEG)
        .select_related("decided_by")
        .order_by("-created_at")
    )

    prod_model = db_versions.filter(status=ModelVersion.StatusChoices.PRODUCTION).first()
    candidate_model = db_versions.filter(status=ModelVersion.StatusChoices.CANDIDATE).first()
    training_model = db_versions.filter(status=ModelVersion.StatusChoices.TRAINING).first()

    previous_model = (
        db_versions.filter(status=ModelVersion.StatusChoices.ARCHIVED, deactivated_at__isnull=False)
        .order_by("-deactivated_at")
        .first()
    )
    last_rejected = db_versions.filter(status=ModelVersion.StatusChoices.REJECTED).first()

    versions_data = [
        {
            "version": m.version,
            "status": m.status,
            "from": _iso(m.activated_at),
            "to": _iso(m.deactivated_at),
            "dice": m.dice,
            "iou": None,  # not stored on ModelVersion
            "hd95": m.hd95,
            "diceMamaMia": None,  # not stored on ModelVersion
            "decision": m.decision,
            "decidedBy": _full_name(m.decided_by),
            "canRestore": m.status == ModelVersion.StatusChoices.ARCHIVED,
        }
        for m in db_versions
    ]

    candidate = None
    if candidate_model:
        better = None
        if prod_model and candidate_model.dice is not None and prod_model.dice is not None:
            better = candidate_model.dice > prod_model.dice
        candidate = {
            "version": candidate_model.version,
            "trainingData": None,  # TODO: needs a training-set size on ModelVersion (or from MLflow)
            "gate": [
                {"rule": "better_hospital", "passed": better},
                {"rule": "not_worse_mamamia", "passed": None},  # TODO: no MAMA-MIA metric stored
                {"rule": "no_large_drop", "passed": None},  # TODO: needs per-case metrics
            ],
            "cases": [],  # TODO: biggest gain/drop need per-case Dice for both models
        }

    overview = {
        "production": {
            "version": prod_model.version if prod_model else "-----",
            "since": _iso(prod_model.activated_at) if prod_model and prod_model.activated_at else None,
            "approvedBy": _full_name(prod_model.decided_by) if prod_model and prod_model.decided_by else "-----",
        },
        "previous": previous_model.version if previous_model else None,
        "correctedShare": {
            "current": _corrected_share(SegmentationResult.objects.filter(model=prod_model)) if prod_model else None,
            "previous": _corrected_share(SegmentationResult.objects.filter(model=previous_model)) if previous_model else None,
        },
        # TODO: needs editing_seconds on SegmentationResult (saved by approve_case)
        "editTime": {"current": 4, "previous": 7},
        "weeklyCorrected": _weekly_corrected(db_versions),
        "next": _next_retraining(db_versions) if not candidate_model and not training_model else None,
        "lastRun": (
            {
                "date": _iso(last_rejected.created_at),
                "version": last_rejected.version,
                # no human decision = the automatic quality gate said no
                "outcome": "rejected_manual" if last_rejected.decided_by else "rejected_gate",
            }
            if last_rejected
            else None
        ),
        "training": (
            # TODO: epoch / epochs / ETA live in the MLflow run (mlops/mlflow_client.py)
            {"version": training_model.version, "epoch": None, "epochs": None, "etaHours": None}
            if training_model
            else None
        ),
        "candidate": candidate,
        "versions": versions_data,
    }

    return Response(overview, status=status.HTTP_200_OK)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def extraction_overview(request):
    prod_ext = ModelVersion.objects.filter(
        module=ModelVersion.ModuleChoices.EXT, status=ModelVersion.StatusChoices.PRODUCTION
    ).first()

    verified = ExtractionResult.objects.filter(status=ExtStatus.APPROVED, accepted_report__isnull=False)

    # how often the doctor changed what the model proposed, per form field
    totals = dict.fromkeys(REPORT_FIELDS, 0)
    changed = dict.fromkeys(REPORT_FIELDS, 0)
    scoped = verified.filter(model=prod_ext) if prod_ext else verified
    for extraction in scoped.only("accepted_report", "generated_report").iterator():
        accepted = _as_fields(extraction.accepted_report)
        generated = _as_fields(extraction.generated_report)
        for key, value in accepted.items():
            if key not in generated:
                continue  # the model proposed nothing for this field (e.g. "curve" is not in the schema)
            totals[key] += 1
            if value != generated[key]:
                changed[key] += 1

    overview = {
        "version": prod_ext.version if prod_ext else None,
        "since": _iso(prod_ext.activated_at) if prod_ext else None,
        "examplePool": verified.count(),
        "fields": [
            {
                "field": FIELD_LABELS[key],
                # TODO: per-field F1 is not stored; ModelVersion.f1 is one number for the whole model
                "f1": None,
                "correctedShare": round(changed[key] / totals[key], 2) if totals[key] else None,
            }
            for key in REPORT_FIELDS
        ],
    }
    return Response(overview, status=status.HTTP_200_OK)


@api_view(["POST"])
@require_permission(["manageModels"])
def promote_model(request, version):
    model_ver = get_object_or_404(ModelVersion, version=version)

    ModelVersion.objects.filter(module=model_ver.module, status=ModelVersion.StatusChoices.PRODUCTION).update(
        status=ModelVersion.StatusChoices.ARCHIVED,
        deactivated_at=timezone.now()
    )

    model_ver.status = ModelVersion.StatusChoices.PRODUCTION
    model_ver.decision = ModelVersion.DecisionChoices.PROMOTED
    model_ver.activated_at = timezone.now()
    model_ver.decided_by = request.user
    model_ver.save()

    record_audit(
        request,
        kind="model_promoted",
        object=str(model_ver.version),
        detail=f"Dice: {model_ver.dice}" if model_ver.dice else None
    )
    return Response(version, status=status.HTTP_200_OK)


@api_view(["POST"])
@require_permission(["manageModels"])
def reject_model(request, version):
    model_ver = get_object_or_404(ModelVersion, version=version)
    reason = request.data.get("reason", "")

    model_ver.status = ModelVersion.StatusChoices.REJECTED
    model_ver.decision = ModelVersion.DecisionChoices.REJECTED
    model_ver.decided_by = request.user
    model_ver.save()

    record_audit(
        request,
        kind="model_rejected",
        object=str(model_ver.version),
        detail=reason or "Odrzucono manualnie"
    )

    return Response(version, status=status.HTTP_200_OK)


@api_view(["POST"])
@require_permission(["manageModels"])
def rollback_model(request, version):
    target_model = get_object_or_404(ModelVersion, version=version)

    ModelVersion.objects.filter(module=target_model.module, status=ModelVersion.StatusChoices.PRODUCTION).update(
        status=ModelVersion.StatusChoices.ARCHIVED,
        deactivated_at=timezone.now()
    )

    target_model.status = ModelVersion.StatusChoices.PRODUCTION
    target_model.decision = ModelVersion.DecisionChoices.PROMOTED
    target_model.activated_at = timezone.now()
    target_model.decided_by = request.user
    target_model.save()

    record_audit(
        request,
        kind="model_rolled_back",
        object=str(target_model.version),
        detail="Przywrócono starszą wersję produkcyjną"
    )

    return Response(version, status=status.HTTP_200_OK)


@api_view(["POST"])
@require_permission(["manageModels"])
def start_training(request):
    current_app.send_task("training.run", kwargs={"training_run_id": 1})

    record_audit(
        request,
        kind="training_started",
        object="v-new",
        detail="Uruchomiono nocny trening na zgromadzonych poprawkach"
    )
    return Response(status=200)