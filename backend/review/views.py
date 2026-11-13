from django.utils import timezone
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from django.shortcuts import get_object_or_404
from django.db import transaction
from django.http import HttpResponse
from django.urls import reverse
import logging
import mimetypes

from audit.utils import record_audit
from common.storage import BUCKET_REPORTS, get_bytes
from patients.models import Study
from patients.orthanc_client import OrthancClient, OrthancUnauthorized, OrthancUnavailable
from extraction.models import ExtractionResult, StatusChoices
from segmentation.models import SegmentationResult
from users.permissions import require_permission

logger = logging.getLogger(__name__)

VERIFIED = (StatusChoices.APPROVED, StatusChoices.CORRECTED)
REPORT_FIELDS = ["birads", "location", "size", "shape", "margin", "curve"]  # = FieldKey on the frontend
BIRADS_ORDER = ["0", "1", "2", "3", "4", "4a", "4b", "4c", "5", "6"]

# report wording -> option keys of the frontend form (frontend/src/review/report.ts)
LOCATION_VALUES = {
    "kwadrant górny-zewnętrzny": "upper_outer",
    "kwadrant górny-wewnętrzny": "upper_inner",
    "kwadrant dolny-zewnętrzny": "lower_outer",
    "kwadrant dolny-wewnętrzny": "lower_inner",
    "centralnie": "central",
}
SHAPE_VALUES = {
    "owalny": "oval",
    "okrągły": "round",
    "nieregularny": "irregular",
}
MARGIN_VALUES = {
    "obwiedziony": "circumscribed",
    "nieostry": "indistinct",
    "zatarty": "obscured",
    "mikropłatowaty": "microlobulated",
    "kątowy": "angular",
    "spikularny": "spiculated",
}
FIELD_VALUES = {"location": LOCATION_VALUES, "shape": SHAPE_VALUES, "margin": MARGIN_VALUES}


def _option(mapping: dict, raw) -> str:
    raw = str(raw)
    return mapping.get(raw.lower(), raw)


def _ui_value(field: str, value) -> str | None:
    """Report wording or an option key -> the option key; unknown values stay as they are."""
    if value is None:
        return None
    value = str(value).strip()
    mapping = FIELD_VALUES.get(field, {})
    if value.lower() in mapping.values():
        return value.lower()
    return mapping.get(value.lower(), value)


def _size_value(wymiary) -> str | None:
    """Samo liczba (pole ma osobną jednostkę); kwalifikator „około/do” się gubi."""
    if not wymiary or not wymiary.get("wartosci"):
        return None
    return f"{max(wymiary['wartosci']):g}"

def _dicom_date(value):
    """DICOM YYYYMMDD -> ISO date, or None when the date is unknown."""
    return f"{value[:4]}-{value[4:6]}-{value[6:8]}" if value and len(value) == 8 else None


def _uncertainty(segmentation, extraction) -> float | None:
    for result in (segmentation, extraction):
        if result is not None and result.uncertainty is not None:
            return float(result.uncertainty)
    return None
 
 
def _user_name(user):
    if not user:
        return ""
    return f"{user.first_name} {user.last_name}".strip() or user.username
 
 
def _seg_ref(study_uid, series_uid, sop_uid):
    """Where the viewer finds a DICOM SEG over DICOMweb, or None when there is none."""
    if not (study_uid and series_uid and sop_uid):
        return None
    return {"studyUid": study_uid, "seriesUid": series_uid, "sopUid": sop_uid}


def _model_seg(segmentation, study_uid):
    if segmentation is None:
        return None
    return _seg_ref(study_uid, segmentation.model_seg_series_uid, segmentation.model_seg_sop_uid)


def _approved_seg(segmentation, study_uid):
    """The approved SEG; approved without changes, the model's own SEG is the same mask."""
    approved = _seg_ref(
        study_uid, segmentation.approved_seg_series_uid, segmentation.approved_seg_sop_uid
    )
    if approved is None and segmentation.status == StatusChoices.APPROVED:
        return _model_seg(segmentation, study_uid)
    return approved


def _main_lesion(report: dict):
    """The lesion with the highest BI-RADS (first one on ties). TODO: pick the one that matches the mask."""
    lesions = report.get("zmiany") or []
    if not lesions:
        return None
 
    def rank(lesion):
        birads = str(lesion.get("birads") or "").lower()
        return BIRADS_ORDER.index(birads) if birads in BIRADS_ORDER else -1
 
    return max(lesions, key=rank)

def _mask_measurements(segmentation) -> dict | None:
    """Measurements the worker stored for the model mask. A corrected mask has none yet (#25)."""
    if segmentation is None or segmentation.status == StatusChoices.CORRECTED:
        return None
    return segmentation.measurements


def _overview_measurements(segmentation) -> dict | None:
    """What the overview shows as "Pomiary z segmentacji" (frontend/src/lesion-overview/api.ts).

    The worker measures the model's mask. For a mask approved without changes that is the approved
    mask; a corrected one is not measured yet (#25), so the model's numbers stand in and say so.
    """
    measured = (segmentation.measurements if segmentation else None) or {}
    size = _largest_mm(measured)
    if size is None or measured.get("volume_ml") is None:
        return None
    total = measured["volume_ml"]
    return {
        "source": "model" if segmentation.status == StatusChoices.CORRECTED else "approved",
        # measurements stored before the largest part was measured have the one volume only
        "largest": {"sizeMm": size, "volumeMl": measured.get("largest_volume_ml", total)},
        "totalMl": total,
    }


def _largest_mm(measured: dict | None) -> float | None:
    dimensions = (measured or {}).get("dimensions_mm")
    return max(dimensions) if dimensions else None


def _report_size_mm(report) -> float | None:
    """Largest dimension of the main lesion in the report, in mm."""
    lesion = _main_lesion(report) if isinstance(report, dict) else None
    size = (lesion or {}).get("wymiary") or {}
    values = [v for v in size.get("wartosci") or [] if isinstance(v, (int, float))]
    if not values:
        return None
    return float(max(values)) * (10 if size.get("jednostka") == "cm" else 1)


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
            fields["location"] = _ui_value("location", obs["lokalizacje"][0])
        if (size := _size_value(obs.get("wymiary"))):
            fields["size"] = size
        if obs.get("ksztalt"):
            fields["shape"] = _ui_value("shape", obs["ksztalt"])
        if obs.get("brzeg"):
            fields["margin"] = _ui_value("margin", obs["brzeg"])
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
                out[key] = str(value).upper() if key == "birads" else _ui_value(key, value)
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

def _report_payload(extraction, study_id):
    """What the review screens show as the report (frontend/src/review/extraction.ts CaseReport).

    {"originalUrl", "result"} once the worker has a result; "pending" while it has none yet, which
    the frontend shows as waiting; None without a report.
    """
    if extraction is None:
        return None
    result = extraction.result
    if result is None and extraction.status == StatusChoices.FAILED:
        result = _failed_result(extraction)  # failed before the pipeline ran, e.g. download
    if result is None:
        return "pending"
    url = reverse("review-report-scan", args=[study_id]) if extraction.report_path else None
    return {"originalUrl": url, "result": result}


def _failed_result(extraction) -> dict:
    """A worker result for a report that failed before extraction, so the screen shows the error."""
    return {
        "source": "",
        "status": "error",
        "data": None,
        "error": extraction.error or "unknown error",
        "warnings": [],
        "text": "",
        "provenance": {
            "ocr_engine": None,
            "ocr_engine_version": None,
            "ocr_mean_confidence": None,
            "orientation_detector": None,
            "page_rotations": [],
            "llm_provider": "",
            "llm_model": "",
            "prompt_version": "",
            "schema_version": "",
        },
        "attempts": 0,
        "ocr_seconds": None,
        "llm_seconds": None,
        "created_at": extraction.updated_at.isoformat() if extraction.updated_at else "",
    }


def _overview_report(extraction, study_id):
    """{source, accepted, lesions} of an approved form, as frontend/src/lesion-overview/api.ts reads it."""
    if extraction is None or not extraction.accepted_report:
        return None
    return {
        "source": _report_payload(extraction, study_id),
        "accepted": extraction.accepted_report,
        "lesions": extraction.lesion_answers or {},
    }


def _is_corrected(lesions, field_checks=None) -> bool:
    """A field changed in the form or in the details below it."""
    in_form = any(
        isinstance(answer, dict) and answer.get("state") == "corrected"
        for fields in lesions.values()
        if isinstance(fields, dict)
        for answer in fields.values()
    )
    return in_form or any(check == "corrected" for check in (field_checks or {}).values())


def _apply_form(extraction, submitted, user):
    """Store the review form: {"report": <worker schema>, "lesions": {index: {field: answer}},
    "fields": {path in the report: "confirmed" | "corrected" | "unverified"}}.

    Without a report the doctor accepts the model's report as it is.
    Sent again, it replaces the last answers.
    """
    submitted = submitted if isinstance(submitted, dict) else {}
    report = submitted.get("report")
    lesions = submitted.get("lesions")
    lesions = lesions if isinstance(lesions, dict) else {}
    field_checks = submitted.get("fields")
    field_checks = field_checks if isinstance(field_checks, dict) else None
    if isinstance(report, dict):
        extraction.accepted_report = report
        extraction.lesion_answers = lesions
        extraction.field_checks = field_checks
    elif not extraction.accepted_report:
        extraction.accepted_report = extraction.generated_report
    corrected = _is_corrected(lesions, field_checks)
    extraction.status = StatusChoices.CORRECTED if corrected else StatusChoices.APPROVED
    extraction.accepted_by = user
    extraction.accepted_at = timezone.now().date()
    extraction.save()


def _audit_object(study) -> str:
    return f"#{str(study.id).zfill(4)}"


def _mask_detail(mask_choice) -> str:
    return "corrected" if mask_choice == "corrected" else "no changes"


def _approve_mask(segmentation, new_status, user) -> bool:
    """Approve the model mask if it waits for review; True when it changed."""
    if not segmentation or segmentation.status not in [StatusChoices.COMPLETED, StatusChoices.REJECTED]:
        return False
    segmentation.status = new_status
    segmentation.accepted_by = user
    segmentation.accepted_at = timezone.now().date()
    segmentation.save()
    return True


def _reopen(result) -> bool:
    """Take back the approval of a mask or a form; True when it changed."""
    if not result or result.status not in VERIFIED:
        return False
    result.status = StatusChoices.COMPLETED
    result.accepted_by = None
    result.accepted_at = None
    result.save()
    return True


@api_view(["GET"])
@require_permission("review")
def report_scan(request, study_id):
    """The uploaded original of the active report (image or .txt), for the preview next to the form."""
    study = get_object_or_404(Study, orthanc_path=study_id)
    extraction = study.extractions.active()
    if not extraction or not extraction.report_path:
        return Response({"detail": "Brak skanu."}, status=status.HTTP_404_NOT_FOUND)
    try:
        data = get_bytes(BUCKET_REPORTS, extraction.report_path)
    except Exception:
        logger.exception("Could not read the report scan of study %s", study.id)
        return Response({"detail": "Brak skanu."}, status=status.HTTP_404_NOT_FOUND)
    content_type = mimetypes.guess_type(extraction.report_path)[0] or "application/octet-stream"
    return HttpResponse(data, content_type=content_type)


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

        queue_data.append({
            "studyId": study.orthanc_path,
            "studyNumber": str(study.id).zfill(4),
            "studyDate": _dicom_date(orthanc_map.get(study.orthanc_path, {}).get("study_date")),
            "uncertainty": _uncertainty(segmentation, extraction),
        })

    # least certain first; unknown uncertainty counts as least certain, so it is not overlooked
    queue_data.sort(key=lambda x: (x["uncertainty"] is not None, -(x["uncertainty"] or 0)))
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



    mask_approved_val = None
    if segmentation:
        if segmentation.status == StatusChoices.APPROVED:
            mask_approved_val = "confirmed"
        elif segmentation.status == StatusChoices.CORRECTED:
            mask_approved_val = "corrected"
    
    measured = _mask_measurements(segmentation)
    proposals = {}
    if extraction and extraction.status not in (StatusChoices.PENDING, StatusChoices.PROCESSING):
        proposals = _proposals(extraction.generated_report)

    case_data = {
        "studyId": study.orthanc_path,
        "studyNumber": str(study.id).zfill(4),
        "patientId": o_study.get("patient_id") or "---",
        "age": None,
        "studyDate": _dicom_date(o_study.get("study_date")),
        "description": o_study.get("description") or None,
        "uncertainty": _uncertainty(segmentation, extraction),
        "segmentationVersion": str(segmentation.model_id) if segmentation and segmentation.model_id else "-",
        "extractionVersion": str(extraction.model_id) if extraction and extraction.model_id else None,
        "studyUid": o_study.get("study_instance_uid"),
        # null while there is no SEG: still processing, rejected, or the model found nothing
        "mask": _model_seg(segmentation, o_study.get("study_instance_uid")),
        "report": _report_payload(extraction, study.orthanc_path),
        "proposals": proposals,
        "measurements": {
            "volume": (measured or {}).get("volume_ml"),
            "size": _largest_mm(measured),
            "sizeInReport": _report_size_mm(extraction.generated_report) if extraction else None,
        },
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

        approved_mask = _approve_mask(segmentation, new_status, request.user)
        approved_form = bool(extraction) and extraction.status in [StatusChoices.COMPLETED, StatusChoices.REJECTED]
        if approved_form:
            _apply_form(extraction, payload, request.user)

    if approved_mask:
        record_audit(request, kind="mask_approved", object=_audit_object(study), detail=_mask_detail(mask_choice))
    if approved_form:
        record_audit(request, kind="form_approved", object=_audit_object(study), detail="zatwierdzono komplet")
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
        approved_mask = _approve_mask(segmentation, new_status, request.user)

    if approved_mask:
        record_audit(request, kind="mask_approved", object=_audit_object(study), detail=_mask_detail(mask_choice))
    return Response(status=status.HTTP_200_OK)


@api_view(["POST"])
@require_permission(["review"])
def reopen_case(request, study_id):
    study = get_object_or_404(Study, orthanc_path=study_id)
    
    with transaction.atomic():
        segmentation = SegmentationResult.objects.select_for_update().filter(study=study).order_by("-id").first()
        reopened_mask = _reopen(segmentation)
        extraction = ExtractionResult.objects.select_for_update().filter(study=study).active()
        reopened_form = _reopen(extraction)

    if reopened_mask:
        record_audit(request, kind="mask_unapproved", object=_audit_object(study), detail="reopened case")
    if reopened_form:
        record_audit(request, kind="form_unapproved", object=_audit_object(study), detail="reopened case")
    return Response(status=status.HTTP_200_OK)


@api_view(["POST"])
@require_permission(["review"])
def unapprove_mask(request, study_id):
    study = get_object_or_404(Study, orthanc_path=study_id)
    
    with transaction.atomic():
        segmentation = SegmentationResult.objects.select_for_update().filter(study=study).order_by("-id").first()
        unapproved = _reopen(segmentation)

    if unapproved:
        record_audit(request, kind="mask_unapproved", object=_audit_object(study))
    return Response(status=status.HTTP_200_OK)


@api_view(["POST"])
@require_permission(["review"])
def approve_form(request, study_id):
    study = get_object_or_404(Study, orthanc_path=study_id)
    submitted = request.data
    
    with transaction.atomic():
        extraction = ExtractionResult.objects.select_for_update().filter(study=study).active()
        # sent again after a later change
        updated = bool(extraction) and extraction.status in VERIFIED
        waiting = bool(extraction) and extraction.status in (
            StatusChoices.COMPLETED,
            StatusChoices.REJECTED,
        )
        approved = updated or waiting
        if approved:
            _apply_form(extraction, submitted, request.user)

    if approved:
        detail = "Form updated" if updated else "Form approved"
        record_audit(request, kind="form_approved", object=_audit_object(study), detail=detail)
    return Response(status=status.HTTP_200_OK)


@api_view(["POST"])
@require_permission(["review"])
def unapprove_form(request, study_id):
    study = get_object_or_404(Study, orthanc_path=study_id)
    
    with transaction.atomic():
        extraction = ExtractionResult.objects.select_for_update().filter(study=study).active()
        unapproved = _reopen(extraction)

    if unapproved:
        record_audit(request, kind="form_unapproved", object=_audit_object(study))
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
 
    measured = _mask_measurements(segmentation)
    by_field = {row["field"]: row["value"] for row in _report_rows(extraction) or []}
 
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
        "masks": {
            "approved": _approved_seg(segmentation, o_data.get("study_instance_uid")),
            "model": _model_seg(segmentation, o_data.get("study_instance_uid")),
        },
        "mask": {
            "corrected": corrected,
            "version": segmentation.model_id,
            "date": accepted_at,
            "by": _user_name(segmentation.accepted_by),
        },
        "measurements": _overview_measurements(segmentation),
        "report": _overview_report(extraction, study.orthanc_path),
        "comparison": [
            {"feature": "largestSize", "fromMask": _largest_mm(measured), "fromReport": by_field.get("size"), "match": None},
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
