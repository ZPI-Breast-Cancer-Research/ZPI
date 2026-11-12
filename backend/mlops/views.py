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

def _person(user):
    if not user:
        return None

    return {
        "login": user.get_username(),
        "name": _full_name(user),
    }

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

    prod_model = db_versions.filter(
        status=ModelVersion.StatusChoices.PRODUCTION
    ).first()

    candidate_model = db_versions.filter(
        status=ModelVersion.StatusChoices.CANDIDATE
    ).first()

    training_model = db_versions.filter(
        status=ModelVersion.StatusChoices.TRAINING
    ).first()

    previous_model = (
        db_versions.filter(
            status=ModelVersion.StatusChoices.ARCHIVED,
            deactivated_at__isnull=False,
        )
        .order_by("-deactivated_at")
        .first()
    )

    # Dane aktualnej wersji produkcyjnej.
    in_use = None

    if prod_model:
        production_results = SegmentationResult.objects.filter(
            model=prod_model
        )

        rejected_count = production_results.filter(
            status=SegStatus.REJECTED
        ).count()

        in_use = {
            "version": prod_model.version,
            "since": _iso(prod_model.activated_at),
            "approvedBy": _person(prod_model.decided_by),
            "studies": (
                production_results
                .values("study_id")
                .distinct()
                .count()
            ),
            "rejected": (
                [{"reason": "rejected", "count": rejected_count}]
                if rejected_count
                else []
            ),
            # Nie mamy metryk Dice dla poszczególnych badań.
            "weakest": None,
        }

    # Dane potrzebne do określenia, czy można rozpocząć trening.
    retraining = _next_retraining(db_versions)

    can_start_training = (
        retraining["corrections"] >= retraining["threshold"]
        and training_model is None
        and candidate_model is None
    )

    training_data = {
        "corrections": retraining["corrections"],
        "threshold": retraining["threshold"],
        "window": retraining["window"],
        "canStart": can_start_training,
        "run": None,
    }

    # Informacje o aktualnie trwającym treningu.
    # Dokładne epoch/ETA wymagają pobrania danych z MLflow.
    if training_model:
        training_data["run"] = {
            "version": training_model.version,
            "epoch": None,
            "epochs": None,
            "etaHours": None,
            # Brak implementacji zatrzymywania treningu w pokazanym backendzie.
            "canStop": False,
        }

    # Mapowanie statusów bazy na statusy oczekiwane przez frontend.
    def map_version_status(model):
        if model.status == ModelVersion.StatusChoices.PRODUCTION:
            return "in_use"

        if model.status == ModelVersion.StatusChoices.ARCHIVED:
            return "retired"

        if model.status == ModelVersion.StatusChoices.REJECTED:
            return "rejected"

        if model.status == ModelVersion.StatusChoices.TRAINING:
            return "training"

        if model.status == ModelVersion.StatusChoices.CANDIDATE:
            if model.decision == ModelVersion.DecisionChoices.PENDING:
                return "proposed"
            return "new"

        return "new"

    # Historia wersji modeli.
    versions_data = []

    for model_version in db_versions:
        model_results = SegmentationResult.objects.filter(
            model=model_version
        )

        metrics = None

        if (
            model_version.dice is not None
            or model_version.hd95 is not None
        ):
            metrics = {
                "set": None,
                "cases": None,
                "dice": model_version.dice,
                "iou": None,
                "hd95": model_version.hd95,
                "diceSmall": None,
                "volumeErrorPct": None,
            }

        # Liczymy zaakceptowane segmentacje dla danej wersji.
        approved_count = model_results.filter(
            status__in=VERIFIED
        ).count()

        corrected_share = _corrected_share(model_results)

        unchanged_share = (
            round(1 - corrected_share, 2)
            if corrected_share is not None
            else None
        )

        periods = []

        if model_version.activated_at:
            periods.append({
                "from": _iso(model_version.activated_at),
                "to": _iso(model_version.deactivated_at),
            })

        agreement = None

        if model_version.activated_at:
            agreement = {
                "approved": approved_count,
                "unchanged": unchanged_share,
                "dice": None,
                "iou": None,
                "volumeMl": None,
            }

        versions_data.append({
            "version": model_version.version,
            "status": map_version_status(model_version),
            "trainedAt": None,
            "trainingCases": None,
            "metrics": metrics,
            "periods": periods,
            "agreement": agreement,
            "proposedBy": None,
            "decidedBy": _person(model_version.decided_by),
            "reason": None,
        })

    overview = {
        "inUse": in_use,

        "compareWith": (
            previous_model.version
            if previous_model
            else None
        ),
        "proposal": None,

        "training": training_data,

        "versions": versions_data,
    }

    return Response(overview, status=status.HTTP_200_OK)

@api_view(["GET"])
@permission_classes([IsAuthenticated])
def extraction_overview(request):
    prod_ext = (
        ModelVersion.objects.filter(
            module=ModelVersion.ModuleChoices.EXT,
            status=ModelVersion.StatusChoices.PRODUCTION,
        )
        .order_by("-activated_at", "-created_at")
        .first()
    )
    extractions = ExtractionResult.objects.all()

    if prod_ext:
        extractions = extractions.filter(model=prod_ext)
    verified = extractions.filter(
        status__in=(
            ExtStatus.APPROVED,
            ExtStatus.CORRECTED,
        ),
        accepted_report__isnull=False,
    )
    failed = extractions.filter(
        status=ExtStatus.FAILED,
    )
    corrected = extractions.filter(
        status=ExtStatus.CORRECTED,
        accepted_report__isnull=False,
    )

    totals = dict.fromkeys(REPORT_FIELDS, 0)
    changed = dict.fromkeys(REPORT_FIELDS, 0)
    for extraction in verified.only(
        "accepted_report",
        "generated_report",
    ).iterator():

        accepted = _as_fields(extraction.accepted_report)
        generated = _as_fields(extraction.generated_report)

        for key, value in accepted.items():
            if key not in generated:
                continue

            totals[key] += 1

            if value != generated[key]:
                changed[key] += 1

    verified_count = verified.count()
    ext_versions = ModelVersion.objects.filter(
    module=ModelVersion.ModuleChoices.EXT,
    ).order_by("-created_at")
    models_data = [
    {
        "version": model.version,
        "status": model.status,
        "createdAt": _iso(model.created_at),
        "activatedAt": _iso(model.activated_at),
    }
    for model in ext_versions
    ]
    overview = {
        "version": prod_ext.version if prod_ext else None,
        "models": models_data,
        "fewShots": [],
        "since": (
            _iso(prod_ext.activated_at)
            if prod_ext and prod_ext.activated_at
            else None
        ),
        "examplePool": verified_count,

        "verifiedDescriptions": verified_count,
        "failedDescriptions": failed.count(),
        "correctedDescriptions": corrected.count(),
        "fields": [
            {
                "field": FIELD_LABELS[key],
                "f1": None,
                "correctedShare": (
                    round(changed[key] / totals[key], 2)
                    if totals[key]
                    else None
                ),
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