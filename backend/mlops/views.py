from django.utils import timezone
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from django.shortcuts import get_object_or_404

from .models import ModelVersion
from users.permissions import require_permission


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def segmentation_overview(request):
    db_versions = ModelVersion.objects.filter(module=ModelVersion.ModuleChoices.SEG).order_by("-created_at")
    
    prod_model = db_versions.filter(status=ModelVersion.StatusChoices.PRODUCTION).first()
    candidate_model = db_versions.filter(status=ModelVersion.StatusChoices.CANDIDATE).first()
    training_model = db_versions.filter(status=ModelVersion.StatusChoices.TRAINING).first()
    
    versions_data = []
    for m in db_versions:
        versions_data.append({
            "version": m.version,
            "status": m.status,
            "from": m.activated_at.strftime("%Y-%m-%d") if m.activated_at else None,
            "to": m.deactivated_at.strftime("%Y-%m-%d") if m.deactivated_at else None,
            "dice": m.dice,
            "iou": None,
            "hd95": m.hd95,
            "diceMamaMia": None,
            "decision": m.decision,
            "decidedBy": f"{m.decided_by.first_name} {m.decided_by.last_name}".strip() if m.decided_by else None,
            "canRestore": m.status == ModelVersion.StatusChoices.ARCHIVED,
        })

    archived_versions = db_versions.filter(status=ModelVersion.StatusChoices.ARCHIVED)
    previous_version = archived_versions.first().version if archived_versions.exists() else None

    overview = {
        "production": {
            "version": prod_model.version if prod_model else "-----",
            "since": prod_model.activated_at.strftime("%Y-%m-%d") if prod_model and prod_model.activated_at else "0000-00-00",
            "approvedBy": f"{prod_model.decided_by.first_name}" if prod_model and prod_model.decided_by else "-----"
        },
        "previous": previous_version,
        "correctedShare": {"current": 0.31, "previous": 0.38},
        "editTime": {"current": 74, "previous": 92},
        "weeklyCorrected": [
            { "week": "2026-08-31", "share": 0.4 },
            { "week": "2026-09-07", "share": 0.37 },
            { "week": "2026-09-14", "share": 0.39 },
            { "week": "2026-09-21", "share": 0.36 },
            { "week": "2026-09-28", "share": 0.38 },
            { "week": "2026-10-05", "share": 0.33, "versionChange": "7" },
            { "week": "2026-10-12", "share": 0.31 },
            { "week": "2026-10-19", "share": 0.3 },
        ],
        "next": { "corrections": 32, "threshold": 50, "window": "2026-10-27T02:00" } if not candidate_model and not training_model else None,
        "lastRun": { "date": "2026-10-19", "version": "5", "outcome": "rejected_gate" },
        "training": {
            "version": training_model.version,
            "epoch": 31,
            "epochs": 50,
            "etaHours": 2
        } if training_model else None,
        "candidate": {
            "version": candidate_model.version,
            "trainingData": 50,
            "gate": [
                { "rule": "better_hospital", "passed": True },
                { "rule": "not_worse_mamamia", "passed": True },
                { "rule": "no_large_drop", "passed": True },
            ],
            "cases": [
                { "studyId": "t31", "studyNumber": "0031", "label": "biggest_gain", "current": None, "candidate": None },
                { "studyId": "t44", "studyNumber": "0044", "label": "gain", "current": None, "candidate": None },
                { "studyId": "t52", "studyNumber": "0052", "label": "biggest_drop", "current": None, "candidate": None },
                { "studyId": "t60", "studyNumber": "0060", "label": "drop", "current": None, "candidate": None },
            ],
        } if candidate_model else None,
        "versions": versions_data,
    }

    return Response(overview, status=status.HTTP_200_OK)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def extraction_overview(request):
    prod_ext = ModelVersion.objects.filter(module=ModelVersion.ModuleChoices.EXT, status=ModelVersion.StatusChoices.PRODUCTION).first()
    
    overview = {
        "version": prod_ext.version if prod_ext else "3",
        "since": prod_ext.activated_at.strftime("%Y-%m-%d") if prod_ext and prod_ext.activated_at else "2026-09-20",
        "examplePool": 46,
        "fields": [
            { "field": "BI-RADS", "f1": prod_ext.f1 if prod_ext else None, "correctedShare": 0.06 },
            { "field": "Lokalizacja", "f1": None, "correctedShare": 0.09 },
            { "field": "Wymiar", "f1": None, "correctedShare": 0.12 },
            { "field": "Kształt", "f1": None, "correctedShare": 0.14 },
            { "field": "Brzegi", "f1": None, "correctedShare": 0.27 },
            { "field": "Krzywa", "f1": None, "correctedShare": 0.11 },
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
    
    return Response(version, status=status.HTTP_200_OK)


@api_view(["POST"])
@require_permission(["manageModels"])
def start_training(request):
    return Response(status=404)