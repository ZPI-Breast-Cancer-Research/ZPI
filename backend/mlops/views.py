from datetime import timedelta

from django.conf import settings
from django.db.models import Count, Q
from django.db.models.functions import TruncWeek
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import status
from rest_framework.decorators import api_view
from rest_framework.response import Response
from celery import current_app

from extraction.models import ExtractionResult, StatusChoices as ExtStatus
from review.views import REPORT_FIELDS, _as_fields
from segmentation.models import SegmentationResult, StatusChoices as SegStatus
from users.permissions import require_permission
from audit.utils import record_audit
from .models import ModelVersion, ModuleUsagePeriod

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


def _in_use_since(model):
    """Start of the open usage period of a version, None when it is not in use."""
    period = model.periods.filter(ended_at__isnull=True).order_by("-started_at").first()
    return period.started_at if period else None


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
    periods = ModuleUsagePeriod.objects.filter(
        module_version__in=db_versions, started_at__date__gte=since
    ).select_related("module_version")
    for period in periods:
        day = timezone.localtime(period.started_at).date()
        activations[day - timedelta(days=day.weekday())] = str(period.module_version.version)

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
@require_permission(["viewModels"])
def segmentation_overview(request):
    db_versions = (
        ModelVersion.objects.filter(module=ModelVersion.ModuleChoices.SEG)
        .select_related("decided_by", "proposed_by")
        .prefetch_related("periods")
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

    # the archived version that was in use last
    last_ended = (
        ModuleUsagePeriod.objects.filter(
            module_version__module=ModelVersion.ModuleChoices.SEG,
            module_version__status=ModelVersion.StatusChoices.ARCHIVED,
            ended_at__isnull=False,
        )
        .select_related("module_version")
        .order_by("-ended_at")
        .first()
    )
    previous_model = last_ended.module_version if last_ended else None

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
            "since": _iso(_in_use_since(prod_model)),
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
            return "proposed"

        return "new"

    # Historia wersji modeli.
    versions_data = []

    for model_version in db_versions:
        model_results = SegmentationResult.objects.filter(
            model=model_version
        )

        metrics = None
        measured = model_version.metrics or {}

        if (
            measured.get("dice") is not None
            or measured.get("hd95") is not None
        ):
            metrics = {
                "set": model_version.dataset or None,
                "cases": model_version.metrics_cases,
                "dice": measured.get("dice"),
                "iou": measured.get("iou"),
                "hd95": measured.get("hd95"),
                "diceSmall": measured.get("dice_small"),
                "volumeErrorPct": measured.get("volume_error_pct"),
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

        periods = [
            {"from": _iso(period.started_at), "to": _iso(period.ended_at)}
            for period in model_version.periods.all()
        ]

        agreement = None

        if periods:
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
            "trainedAt": _iso(model_version.trained_at),
            "trainingCases": model_version.training_cases,
            "metrics": metrics,
            "periods": periods,
            "agreement": agreement,
            "proposedBy": _person(model_version.proposed_by),
            "decidedBy": _person(model_version.decided_by),
            "reason": model_version.reason or None,
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
@require_permission(["viewModels"])
def extraction_overview(request):
    prod_ext = (
        ModelVersion.objects.filter(
            module=ModelVersion.ModuleChoices.EXT,
            status=ModelVersion.StatusChoices.PRODUCTION,
        )
        .order_by("-created_at")
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
    ext_versions = (
        ModelVersion.objects.filter(module=ModelVersion.ModuleChoices.EXT)
        .prefetch_related("periods")
        .order_by("-created_at")
    )
    models_data = [
        {
            "version": model.version,
            "status": model.status,
            "createdAt": _iso(model.created_at),
            # start of the last period the version was in use
            "activatedAt": _iso(max((p.started_at for p in model.periods.all()), default=None)),
        }
        for model in ext_versions
    ]
    overview = {
        "version": prod_ext.version if prod_ext else None,
        "models": models_data,
        "fewShots": [],
        "since": _iso(_in_use_since(prod_ext)) if prod_ext else None,
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

def _segmentation_version(version):
    """These endpoints act on segmentation; extraction can have the same version number."""
    return get_object_or_404(ModelVersion, module=ModelVersion.ModuleChoices.SEG, version=version)


# a version that waits for a decision: a draft or a proposal
UNDECIDED = (ModelVersion.StatusChoices.NEW, ModelVersion.StatusChoices.CANDIDATE)


def _wrong_status(model, allowed):
    """409 when the version is not in a status the action applies to, otherwise None."""
    if model.status in allowed:
        return None
    return Response(
        {
            "code": "wrong_status",
            "detail": f"Wersja {model.version} ma status „{model.get_status_display()}”, "
                      "tej operacji nie można na niej wykonać.",
        },
        status=status.HTTP_409_CONFLICT,
    )


@api_view(["POST"])
@require_permission(["manageModels"])
def promote_model(request, version):
    model_ver = _segmentation_version(version)
    refused = _wrong_status(model_ver, UNDECIDED)
    if refused:
        return refused
    model_ver.put_in_use(request.user, reason=request.data.get("reason", ""))

    dice = model_ver.metrics.get("dice")
    record_audit(
        request,
        kind="model_promoted",
        object=str(model_ver.version),
        detail=f"Dice: {dice}" if dice else None
    )
    return Response(version, status=status.HTTP_200_OK)


@api_view(["POST"])
@require_permission(["manageModels"])
def reject_model(request, version):
    model_ver = _segmentation_version(version)
    # the version in use is replaced by promoting another one, never rejected
    refused = _wrong_status(model_ver, UNDECIDED)
    if refused:
        return refused
    reason = request.data.get("reason", "")

    model_ver.status = ModelVersion.StatusChoices.REJECTED
    model_ver.decided_by = request.user
    model_ver.reason = reason
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
    target_model = _segmentation_version(version)
    refused = _wrong_status(target_model, (ModelVersion.StatusChoices.ARCHIVED,))
    if refused:
        return refused
    target_model.put_in_use(request.user, reason=request.data.get("reason", ""))

    record_audit(
        request,
        kind="model_rolled_back",
        object=str(target_model.version),
        detail="Przywrócono starszą wersję produkcyjną"
    )

    return Response(version, status=status.HTTP_200_OK)


@api_view(["POST"])
@require_permission(["proposeModels"])
def start_training(request):
    current_app.send_task("training.run", kwargs={"training_run_id": 1})

    record_audit(
        request,
        kind="training_started",
        object="v-new",
        detail="Uruchomiono nocny trening na zgromadzonych poprawkach"
    )
    return Response(status=200)