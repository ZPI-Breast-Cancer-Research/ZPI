from django.utils import timezone
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from django.shortcuts import get_object_or_404

from patients.models import Study
from patients.orthanc_client import OrthancClient, OrthancUnauthorized, OrthancUnavailable
from extraction.models import ExtractionResult, StatusChoices
from segmentation.models import SegmentationResult
from users.permissions import require_permission


@api_view(["GET"])
@require_permission(["review"])
def review_queue(request):
    """Zwraca kolejkę badań do weryfikacji na podstawie rzeczywistych modeli, posortowaną od najmniej pewnych."""
    studies = Study.objects.all()
    queue_data = []
    
    try:
        orthanc_client = OrthancClient()
        orthanc_studies = orthanc_client.list_studies()
        orthanc_map = {o.get("orthanc_id"): o for o in orthanc_studies}
    except (OrthancUnauthorized, OrthancUnavailable):
        orthanc_map = {}

    for study in studies:
        segmentation = SegmentationResult.objects.filter(study=study).first()
        extraction = ExtractionResult.objects.filter(study=study).first()
        
        # Pomijamy badania, które są już w pełni zatwierdzone lub poprawione
        seg_status = segmentation.status if segmentation else StatusChoices.PENDING
        ext_status = extraction.status if extraction else StatusChoices.PENDING
        
        if seg_status in [StatusChoices.APPROVED, StatusChoices.CORRECTED] and \
           ext_status in [StatusChoices.APPROVED, StatusChoices.CORRECTED]:
            continue

        uncertainty = 0.5
        if segmentation and segmentation.uncertainty is not None:
            uncertainty = float(segmentation.uncertainty)
        elif extraction and extraction.uncertainty is not None:
            uncertainty = float(extraction.uncertainty)

        o_data = orthanc_map.get(study.orthanc_path, {})
        study_date = o_data.get("study_date")
        formatted_date = f"{study_date[:4]}-{study_date[4:6]}-{study_date[6:]}" if study_date and len(study_date) == 8 else "2026-10-26"

        queue_data.append({
            "studyId": study.orthanc_path,
            "studyNumber": str(study.id).zfill(4),
            "studyDate": formatted_date,
            "uncertainty": uncertainty,
        })

    queue_data.sort(key=lambda x: x["uncertainty"], reverse=True)
    return Response(queue_data, status=status.HTTP_200_OK)


@api_view(["GET"])
@require_permission(["review"])
def review_case_detail(request, study_id):
    if study_id.isdigit():
        study = get_object_or_404(Study, id=int(study_id))
    else:
        study = Study.objects.filter(orthanc_path=study_id).first()
        if not study:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)

    segmentation = SegmentationResult.objects.filter(study=study).first()
    extraction = ExtractionResult.objects.filter(study=study).first()

    try:
        orthanc_client = OrthancClient()
        o_studies = orthanc_client.list_studies()
        o_study = next((s for s in o_studies if s.get("orthanc_id") == study.orthanc_path), {})
    except (OrthancUnauthorized, OrthancUnavailable):
        o_study = {}

    study_date = o_study.get("study_date")
    formatted_date = f"{study_date[:4]}-{study_date[4:6]}-{study_date[6:]}" if study_date and len(study_date) == 8 else "2026-10-26"

    uncertainty = 0.5
    if segmentation and segmentation.uncertainty is not None:
        uncertainty = float(segmentation.uncertainty)
    elif extraction and extraction.uncertainty is not None:
        uncertainty = float(extraction.uncertainty)

    report_data = extraction.generated_report if extraction and extraction.generated_report else [
        {"text": "Treść opisu badania: "},
        {"text": "lokalizacja", "field": "location"},
        {"text": ", "},
        {"text": "kształt", "field": "shape"},
        {"text": ", "},
        {"text": "brzegi", "field": "margin"},
        {"text": ", "},
        {"text": "wymiar", "field": "size"},
        {"text": ", "},
        {"text": "krzywa", "field": "curve"},
        {"text": ", "},
        {"text": "BI-RADS", "field": "birads"},
        {"text": "."},
    ]

    mask_approved_val = None
    if segmentation:
        if segmentation.status == StatusChoices.APPROVED:
            mask_approved_val = "confirmed"
        elif segmentation.status == StatusChoices.CORRECTED:
            mask_approved_val = "corrected"

    case_data = {
        "studyId": study.orthanc_path,
        "studyNumber": str(study.id).zfill(4),
        "patientId": o_study.get("patient_id") or "P-0101",
        "age": None,
        "studyDate": formatted_date,
        "description": o_study.get("description") or "MR piersi z kontrastem",
        "uncertainty": uncertainty,
        "segmentationVersion": str(segmentation.model_id) if segmentation and segmentation.model_id else "7",
        "extractionVersion": str(extraction.model_id) if extraction and extraction.model_id else None,
        "studyUid": o_study.get("study_instance_uid"),
        "mask": {"center": [0.69, 0.585, 0.53], "radius": [16, 9, 10]},
        "report": report_data,
        "proposals": {
            "birads": {"value": "4C"},
            "location": {"value": "KGZ"},
            "size": {"value": "14"},
            "shape": {"value": "Gładkie"},
            "margin": {"value": "Nieregularne", "disagreement": True},
            "curve": {"value": "Wash-out"},
        },
        "measurements": {"volume": None, "size": None, "sizeInReport": None},
        "maskApproved": mask_approved_val,
    }

    return Response(case_data, status=status.HTTP_200_OK)


@api_view(["POST"])
@require_permission(["review"])
def approve_case(request, study_id):
    study = get_object_or_404(Study, orthanc_path=study_id)
    payload = request.data
    mask_choice = payload.get("mask", "confirmed")
    new_status = StatusChoices.APPROVED if mask_choice == "confirmed" else StatusChoices.CORRECTED

    segmentation = SegmentationResult.objects.filter(study=study).first()
    if segmentation:
        segmentation.status = new_status
        segmentation.accepted_by = request.user
        segmentation.accepted_at = timezone.now().date()
        segmentation.save()


    extraction = ExtractionResult.objects.filter(study=study).first()
    if extraction:
        extraction.status = StatusChoices.APPROVED
        extraction.accepted_by = request.user
        extraction.accepted_at = timezone.now().date()
        extraction.save()

    return Response(status=status.HTTP_200_OK)


@api_view(["POST"])
@require_permission(["review"])
def approve_mask(request, study_id):
    study = get_object_or_404(Study, orthanc_path=study_id)
    payload = request.data
    mask_choice = payload.get("mask", "confirmed")
    new_status = StatusChoices.APPROVED if mask_choice == "confirmed" else StatusChoices.CORRECTED

    segmentation = SegmentationResult.objects.filter(study=study).first()
    if segmentation:
        segmentation.status = new_status
        segmentation.accepted_by = request.user
        segmentation.accepted_at = timezone.now().date()
        segmentation.save()

    return Response(status=status.HTTP_200_OK)


@api_view(["POST"])
@require_permission(["review"])
def reopen_case(request, study_id):
    study = get_object_or_404(Study, orthanc_path=study_id)
    
    SegmentationResult.objects.filter(study=study).update(
        status=StatusChoices.COMPLETED, accepted_by=None, accepted_at=None
    )
    ExtractionResult.objects.filter(study=study).update(
        status=StatusChoices.COMPLETED, accepted_by=None, accepted_at=None
    )

    return Response(status=status.HTTP_200_OK)


@api_view(["POST"])
@require_permission(["review"])
def unapprove_mask(request, study_id):
    study = get_object_or_404(Study, orthanc_path=study_id)
    segmentation = SegmentationResult.objects.filter(study=study).first()
    if segmentation:
        segmentation.status = StatusChoices.COMPLETED
        segmentation.accepted_by = None
        segmentation.accepted_at = None
        segmentation.save()

    return Response(status=status.HTTP_200_OK)


@api_view(["POST"])
@require_permission(["review"])
def approve_form(request, study_id):
    study = get_object_or_404(Study, orthanc_path=study_id)
    extraction = ExtractionResult.objects.filter(study=study).first()
    if extraction:
        extraction.status = StatusChoices.APPROVED
        extraction.accepted_by = request.user
        extraction.accepted_at = timezone.now().date()
        extraction.save()

    return Response(status=status.HTTP_200_OK)


@api_view(["POST"])
@require_permission(["review"])
def unapprove_form(request, study_id):
    study = get_object_or_404(Study, orthanc_path=study_id)
    extraction = ExtractionResult.objects.filter(study=study).first()
    if extraction:
        extraction.status = StatusChoices.COMPLETED
        extraction.accepted_by = None
        extraction.accepted_at = None
        extraction.save()

    return Response(status=status.HTTP_200_OK)
