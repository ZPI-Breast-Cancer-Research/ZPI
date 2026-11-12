from django.utils import timezone
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from django.shortcuts import get_object_or_404
from django.db import transaction

from patients.models import Study
from patients.orthanc_client import OrthancClient, OrthancUnauthorized, OrthancUnavailable
from extraction.models import ExtractionResult, StatusChoices
from segmentation.models import SegmentationResult
from users.permissions import require_permission

VERIFIED = (StatusChoices.APPROVED, StatusChoices.CORRECTED)
REPORT_FIELDS = ["birads", "location", "size", "shape", "margin", "curve"]  # = FieldKey on the frontend
BIRADS_ORDER = ["0", "1", "2", "3", "4", "4a", "4b", "4c", "5", "6"]

LOCATION_VALUES = {
    "kwadrant górny-zewnętrzny": "KGZ",
    "kwadrant górny-wewnętrzny": "KGW",   # sprawdź
    "kwadrant dolny-zewnętrzny": "KDZ",   # sprawdź
    "kwadrant dolny-wewnętrzny": "KDW",   # sprawdź
}
SHAPE_VALUES = {}
MARGIN_VALUES = {}


def _option(mapping: dict, raw) -> str:
    raw = str(raw)
    return mapping.get(raw.lower(), raw.capitalize())


def _size_value(wymiary) -> str | None:
    """Samo liczba (pole ma osobną jednostkę); kwalifikator „około/do” się gubi."""
    if not wymiary or not wymiary.get("wartosci"):
        return None
    return f"{max(wymiary['wartosci']):g}"

def _dicom_date(value):
    return f"{value[:4]}-{value[4:6]}-{value[6:8]}" if value and len(value) == 8 else ""
 
 
def _user_name(user):
    if not user:
        return ""
    return f"{user.first_name} {user.last_name}".strip() or user.username
 
 
def _main_lesion(report: dict):
    """The lesion with the highest BI-RADS (first one on ties). TODO: pick the one that matches the mask."""
    lesions = report.get("zmiany") or []
    if not lesions:
        return None
 
    def rank(lesion):
        birads = lesion.get("birads")
        return BIRADS_ORDER.index(birads) if birads in BIRADS_ORDER else -1
 
    return max(lesions, key=rank)

def _proposals(report) -> dict:
    """{"birads": "4C"} -> {"birads": {"value": "4C"}} (kształt, którego oczekuje front)."""
    return {key: {"value": value} for key, value in _as_fields(report).items()}
 
def _size_text(wymiary) -> str | None:
    if not wymiary or not wymiary.get("wartosci"):
        return None
    text = f"{max(wymiary['wartosci']):g} {wymiary.get('jednostka', 'mm')}"
    qualifier = wymiary.get("kwalifikator")
    return text if qualifier in (None, "dokładny") else f"{qualifier} {text}"
 
 
def _fields_from_schema(report: dict) -> dict:
    """EkstrakcjaBadania JSON -> {birads, location, size, shape, margin} of the main lesion."""
    lesion = _main_lesion(report)
    fields = {}
 
    birads = (lesion or {}).get("birads") or (report.get("wniosek") or {}).get("birads")
    if birads:
        fields["birads"] = str(birads).upper()  # "4c" -> "4C", like in the UI
 
    observations = (lesion or {}).get("obserwacje") or []
    obs = next((o for o in observations if o.get("wymiary")), observations[0] if observations else None)
    if obs:
        if obs.get("lokalizacje"):
            first = obs["lokalizacje"][0]
            fields["location"] = LOCATION_VALUES.get(first, first)
        if (size := _size_value(obs.get("wymiary"))):
            fields["size"] = size
        if obs.get("ksztalt"):
            fields["shape"] = _option(SHAPE_VALUES, obs["ksztalt"])
        if obs.get("brzeg"):
            fields["margin"] = _option(MARGIN_VALUES, obs["brzeg"])
    return fields
 
 
def _as_fields(report) -> dict:
    """Accepts both shapes: the flat form saved by the doctor and the LLM schema."""
    if not isinstance(report, dict):
        return {}
    if any(key in report for key in REPORT_FIELDS):  # flat: {"birads": "4C", ...}
        out = {}
        for key in REPORT_FIELDS:
            value = report.get(key)
            if isinstance(value, dict):
                value = value.get("value")
            if value is not None:
                out[key] = str(value)
        return out
    return _fields_from_schema(report)
 
 
def _report_rows(extraction):
    """[{field, value, corrected}]: accepted values, 'corrected' when they differ from the LLM's."""
    if extraction is None or not extraction.accepted_report:
        return None
    accepted = _as_fields(extraction.accepted_report)
    generated = _as_fields(extraction.generated_report)
    return [
        {"field": key, "value": accepted[key], "corrected": accepted[key] != generated.get(key)}
        for key in REPORT_FIELDS
        if key in accepted
    ]

def _apply_form(extraction, submitted, user):
    new_status = StatusChoices.APPROVED
    if isinstance(submitted, dict) and submitted:
        extraction.accepted_report = _as_fields(submitted)  # obsługuje {"value": ...}
        if any(isinstance(v, dict) and v.get("state") == "corrected" for v in submitted.values()):
            new_status = StatusChoices.CORRECTED
    extraction.status = new_status
    extraction.accepted_by = user
    extraction.accepted_at = timezone.now().date()
    extraction.save()


@api_view(["GET"])
@require_permission("review")
def review_queue(request):
    """Studies waiting for review: at least one automatic step is COMPLETED, least certain first."""
    # prefilter in the database: only studies that have something COMPLETED
    seg_done = SegmentationResult.objects.filter(
        status=StatusChoices.COMPLETED
    ).values("study_id")
    ext_done = ExtractionResult.objects.filter(
        status=StatusChoices.COMPLETED
    ).values("study_id")
    all_ids = set([item["study_id"] for item in seg_done]).union([item["study_id"] for item in ext_done])
    studies = list(Study.objects.filter(id__in=all_ids))

    if not studies:
        return Response([], status=status.HTTP_200_OK)

    # newest segmentation and active report per study, two queries for all of them
    study_ids = [s.id for s in studies]
    segmentations = {
        s.study_id: s for s in SegmentationResult.objects.filter(study_id__in=study_ids).order_by("id")
    }
    extractions = {
        e.study_id: e
        for e in ExtractionResult.objects.filter(study_id__in=study_ids).oldest_assigned_first()
    }

    try:
        studies_orth = OrthancClient().list_studies()
        orthanc_map = {o.get("orthanc_id"): o for o in studies_orth}
    except OrthancUnavailable:  # includes OrthancUnauthorized
        orthanc_map = {}

    queue_data = []
    for study in studies:
        segmentation = segmentations.get(study.id)
        extraction = extractions.get(study.id)

        # the prefilter looked at any result; here we check the newest / active one
        seg_status = segmentation.status if segmentation else None
        ext_status = extraction.status if extraction else None
        if StatusChoices.COMPLETED not in (seg_status, ext_status):
            continue

        uncertainty = 0.00
        if segmentation and segmentation.uncertainty is not None:
            uncertainty = float(segmentation.uncertainty)
        elif extraction and extraction.uncertainty is not None:
            uncertainty = float(extraction.uncertainty)

        study_date = orthanc_map.get(study.orthanc_path, {}).get("study_date")
        formatted_date = (
            f"{study_date[:4]}-{study_date[4:6]}-{study_date[6:]}"
            if study_date and len(study_date) == 8
            else "----------"
        )

        queue_data.append({
            "studyId": study.orthanc_path,
            "studyNumber": str(study.id).zfill(4),
            "studyDate": formatted_date,
            "uncertainty": float(uncertainty),
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

    segmentation = SegmentationResult.objects.filter(study=study).order_by("-id").first()
    extraction = ExtractionResult.objects.filter(study=study).active()

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

    mask_approved_val = None
    if segmentation:
        if segmentation.status == StatusChoices.APPROVED:
            mask_approved_val = "confirmed"
        elif segmentation.status == StatusChoices.CORRECTED:
            mask_approved_val = "corrected"
    
    proposals = {}
    if extraction and extraction.status not in (StatusChoices.PENDING, StatusChoices.PROCESSING):
        proposals = _proposals(extraction.generated_report)

    case_data = {
        "studyId": study.orthanc_path,
        "studyNumber": str(study.id).zfill(4),
        "patientId": o_study.get("patient_id") or "---",
        "age": None,
        "studyDate": formatted_date,
        "description": o_study.get("description") or "MR piersi z kontrastem",
        "uncertainty": uncertainty,
        "segmentationVersion": str(segmentation.model_id) if segmentation and segmentation.model_id else "-",
        "extractionVersion": str(extraction.model_id) if extraction and extraction.model_id else None,
        "studyUid": o_study.get("study_instance_uid"),
        "mask": {"center": [0.69, 0.585, 0.53], "radius": [16, 9, 10]},
        "report": extraction.report_path if extraction else None,
        "proposals": proposals,
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

    with transaction.atomic():
        segmentation = SegmentationResult.objects.select_for_update().filter(study=study).order_by("-id").first()
        extraction = ExtractionResult.objects.select_for_update().filter(study=study).active()

        if segmentation and segmentation.status in [StatusChoices.COMPLETED,StatusChoices.REJECTED]:
            segmentation.status = new_status
            segmentation.accepted_by = request.user
            segmentation.accepted_at = timezone.now().date()
            segmentation.save()

        if extraction and extraction.status in [StatusChoices.COMPLETED,StatusChoices.REJECTED]:
            _apply_form(extraction, payload.get("fields"), request.user)

    return Response(status=status.HTTP_200_OK)


@api_view(["POST"])
@require_permission(["review"])
def approve_mask(request, study_id):
    study = get_object_or_404(Study, orthanc_path=study_id)
    payload = request.data
    mask_choice = payload.get("mask", "confirmed")
    new_status = StatusChoices.APPROVED if mask_choice == "confirmed" else StatusChoices.CORRECTED

    with transaction.atomic():
        segmentation = SegmentationResult.objects.select_for_update().filter(study=study).order_by("-id").first()
        if segmentation and segmentation.status in [StatusChoices.COMPLETED,StatusChoices.REJECTED]:
            segmentation.status = new_status
            segmentation.accepted_by = request.user
            segmentation.accepted_at = timezone.now().date()
            segmentation.save()

    return Response(status=status.HTTP_200_OK)


@api_view(["POST"])
@require_permission(["review"])
def reopen_case(request, study_id):
    study = get_object_or_404(Study, orthanc_path=study_id)
    
    with transaction.atomic():
        segmentation = SegmentationResult.objects.select_for_update().filter(study=study).order_by("-id").first()
        if segmentation and segmentation.status in (StatusChoices.APPROVED, StatusChoices.CORRECTED):
            segmentation.status = StatusChoices.COMPLETED
            segmentation.accepted_by = None
            segmentation.accepted_at = None
            segmentation.save()
        extraction = ExtractionResult.objects.select_for_update().filter(study=study).active()
        if extraction and extraction.status in (StatusChoices.APPROVED, StatusChoices.CORRECTED):
            extraction.status = StatusChoices.COMPLETED
            extraction.accepted_by = None
            extraction.accepted_at = None
            extraction.save()

    return Response(status=status.HTTP_200_OK)


@api_view(["POST"])
@require_permission(["review"])
def unapprove_mask(request, study_id):
    study = get_object_or_404(Study, orthanc_path=study_id)
    
    with transaction.atomic():
        segmentation = SegmentationResult.objects.select_for_update().filter(study=study).order_by("-id").first()
        if segmentation and segmentation.status in (StatusChoices.APPROVED, StatusChoices.CORRECTED):
            segmentation.status = StatusChoices.COMPLETED
            segmentation.accepted_by = None
            segmentation.accepted_at = None
            segmentation.save()

    return Response(status=status.HTTP_200_OK)


@api_view(["POST"])
@require_permission(["review"])
def approve_form(request, study_id):
    study = get_object_or_404(Study, orthanc_path=study_id)
    submitted = request.data.get("fields")
    
    with transaction.atomic():
        extraction = ExtractionResult.objects.select_for_update().filter(study=study).active()
        if extraction and extraction.status in [StatusChoices.COMPLETED,StatusChoices.REJECTED]:
            _apply_form(extraction, submitted, request.user)

    return Response(status=status.HTTP_200_OK)


@api_view(["POST"])
@require_permission(["review"])
def unapprove_form(request, study_id):
    study = get_object_or_404(Study, orthanc_path=study_id)
    
    with transaction.atomic():
        extraction = ExtractionResult.objects.select_for_update().filter(study=study).active()
        if extraction and extraction.status in (StatusChoices.APPROVED, StatusChoices.CORRECTED):
            extraction.status = StatusChoices.COMPLETED
            extraction.accepted_by = None
            extraction.accepted_at = None
            extraction.save()

    return Response(status=status.HTTP_200_OK)

@api_view(["GET"])
@require_permission("review")
def review_overview(request, study_id):
    """Summary of a verified case; study_id is the Orthanc id, like in review_queue."""
    study = get_object_or_404(Study, orthanc_path=study_id)
 
    segmentation = study.segmentations.select_related("accepted_by").order_by("-id").first()
    extraction = study.extractions.select_related("accepted_by").active()
 
    if segmentation is None or segmentation.status not in VERIFIED:
        return Response(
            {"code": "not_verified", "detail": "Badanie nie zostało jeszcze zweryfikowane."},
            status=status.HTTP_409_CONFLICT,
        )
    try:
        o_data = next(
            (s for s in OrthancClient().list_studies() if s.get("orthanc_id") == study.orthanc_path), {}
        )
    except OrthancUnavailable:  # includes OrthancUnauthorized
        o_data = {}

    corrected = segmentation.status == StatusChoices.CORRECTED
    saving = corrected and not segmentation.accepted_path
 
    report = _report_rows(extraction)
    by_field = {row["field"]: row["value"] for row in report or []}
 
    seg_version = str(segmentation.model_id) if segmentation.model_id else None
    ext_version = str(extraction.model_id) if extraction and extraction.model_id else None
    accepted_at = segmentation.accepted_at.isoformat() if segmentation.accepted_at else ""
 
    return Response({
        "studyId": study.orthanc_path,
        "studyNumber": str(study.id).zfill(4),
        "patientId": o_data.get("patient_id") or "—",
        "age": None, 
        "studyDate": _dicom_date(o_data.get("study_date")),
        "description": o_data.get("description") or "",
        "status": "saving" if saving else "verified",
        "studyUid": o_data.get("study_instance_uid"),
        # TODO: needs the mask geometry (center/radius) or a file endpoint
        "masks": { "approved": {"center": [0.69, 0.585, 0.53], "radius": [16, 9, 10]}, "model": {"center": [0.69, 0.585, 0.53], "radius": [16, 9, 10]} },
        "mask": {
            "corrected": corrected,
            "version": segmentation.model_id,
            "date": accepted_at,
            "by": _user_name(segmentation.accepted_by),
        },
        # TODO: has to be computed from the mask
        "measurements": {"volume": None, "dimensions": None, "intensity": None},
        "report": report,
        "comparison": [
            {"feature": "largestSize", "fromMask": None, "fromReport": by_field.get("size"), "match": None},
            {"feature": "quadrant", "fromMask": None, "fromReport": by_field.get("location"), "match": None},
        ],
        "verification": {
            "by": _user_name(segmentation.accepted_by),
            "date": accepted_at,
            "editingSeconds": None,  # no such field in the models yet
            "segmentationVersion": seg_version,
            "extractionVersion": ext_version,
        },
    })
