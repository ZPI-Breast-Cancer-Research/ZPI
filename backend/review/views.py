from django.utils import timezone
from rest_framework import status
from rest_framework.decorators import api_view
from rest_framework.response import Response
from django.shortcuts import get_object_or_404
from django.db import transaction
from django.http import HttpResponse
from django.urls import reverse

from patients.models import Study
from patients.orthanc_client import OrthancClient, OrthancUnauthorized, OrthancUnavailable
from extraction.models import ExtractionResult, StatusChoices
from segmentation.models import SegmentationResult
from users.permissions import require_permission
from audit.utils import record_audit
import json
import logging

from common.storage import BUCKET_REPORTS, get_bytes

logger = logging.getLogger(__name__)

VERIFIED = (StatusChoices.APPROVED, StatusChoices.CORRECTED)
REPORT_FIELDS = ["birads", "location", "size", "shape", "margin", "curve"]
BIRADS_ORDER = ["0", "1", "2", "3", "4", "4a", "4b", "4c", "5", "6"]

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


def _option(mapping: dict, raw) -> str:
    raw = str(raw)
    return mapping.get(raw.lower(), raw)


def _size_value(wymiary) -> str | None:
    """Sama liczba (pole ma osobną jednostkę); kwalifikator „około/do” się gubi."""
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


def _unwrap_extraction(report):
    if not isinstance(report, dict):
        return {}

    if isinstance(report.get("result"), dict):
        report = report["result"]

    if isinstance(report.get("data"), dict):
        report = report["data"]

    return report


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
    if segmentation is None:
        return None

    approved = _seg_ref(
        study_uid, segmentation.approved_seg_series_uid, segmentation.approved_seg_sop_uid
    )
    if approved is None and segmentation.status == StatusChoices.APPROVED:
        return _model_seg(segmentation, study_uid)
    return approved


def _main_lesion(report: dict):
    report = _unwrap_extraction(report)

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


def _ui_value(field: str, value):
    if value is None:
        return None

    value = str(value).strip()

    mappings = {
        "location": LOCATION_VALUES,
        "shape": SHAPE_VALUES,
        "margin": MARGIN_VALUES,
    }

    mapping = mappings.get(field, {})
    reverse_mapping = {v: v for v in mapping.values()}

    return mapping.get(value.lower(), reverse_mapping.get(value.lower(), value))


def _fields_from_schema(report: dict) -> dict:
    """Polski schemat ekstrakcji -> wartości zgodne z formularzem frontendu."""
    report = _unwrap_extraction(report)
    lesion = _main_lesion(report)
    fields = {}

    birads = (
        (lesion or {}).get("birads")
        or (report.get("wniosek") or {}).get("birads")
    )

    if birads:
        fields["birads"] = str(birads).upper()

    observations = (lesion or {}).get("obserwacje") or []

    if not observations:
        return fields

    obs = next(
        (o for o in observations if o.get("wymiary")),
        observations[0],
    )

    locations = obs.get("lokalizacje") or []
    if locations:
        fields["location"] = _ui_value("location", locations[0])

    if (size := _size_value(obs.get("wymiary"))) is not None:
        fields["size"] = size

    if obs.get("ksztalt"):
        fields["shape"] = _ui_value("shape", obs["ksztalt"])

    if obs.get("brzeg"):
        fields["margin"] = _ui_value("margin", obs["brzeg"])

    return fields


def _as_fields(report) -> dict:
    if not isinstance(report, dict):
        return {}

    if any(key in report for key in REPORT_FIELDS):
        out = {}

        for key in REPORT_FIELDS:
            value = report.get(key)

            if isinstance(value, dict):
                value = value.get("value")

            if value is not None:
                if key == "birads":
                    value = str(value).upper()
                else:
                    value = _ui_value(key, value)

                out[key] = str(value)

        return out
    return _fields_from_schema(report)


def _load_case_report(extraction, study_id):
    """Load the legacy MinIO report wrapper and expose its scan URL, when present."""
    if not extraction or not extraction.report_path:
        return None
    try:
        report = json.loads(get_bytes(BUCKET_REPORTS, extraction.report_path))
    except Exception:
        logger.exception("Nie udało się wczytać raportu %s", extraction.report_path)
        return None

    scan_key = report.pop("scanKey", None)  # klucz w MinIO nie wychodzi do przeglądarki

    if not isinstance(report.get("result"), dict):
        report = {"result": report}

    report["originalUrl"] = reverse("review-report-scan", args=[study_id]) if scan_key else None
    return report


@api_view(["GET"])
@require_permission("review")
def report_scan(request, study_id):
    study = get_object_or_404(Study, orthanc_path=study_id)
    extraction = study.extractions.order_by("-id").first()
    try:
        report = json.loads(get_bytes(BUCKET_REPORTS, extraction.report_path))
        key = report.get("scanKey")
        if not key:
            return Response({"detail": "Brak skanu."}, status=status.HTTP_404_NOT_FOUND)
        data = get_bytes(BUCKET_REPORTS, key)
    except Exception:
        logger.exception("Nie udało się wczytać skanu badania %s", study_id)
        return Response({"detail": "Brak skanu."}, status=status.HTTP_404_NOT_FOUND)
    return HttpResponse(data, content_type="image/png")


def _answers(extraction) -> dict:
    """FieldAnswers: {field: {"value", "state"}}; corrected when it differs from the LLM proposal."""
    accepted = _as_fields(extraction.accepted_report)
    generated = _as_fields(extraction.generated_report)
    return {
        key: {
            "value": accepted[key],
            "state": "corrected" if accepted[key] != generated.get(key) else "confirmed",
        }
        for key in REPORT_FIELDS
        if key in accepted
    }


def _report_payload(extraction, study_id=None):
    """Return the report shape expected by the review screens."""
    if extraction is None:
        return None

    result = extraction.result
    if result is None and extraction.status == StatusChoices.FAILED:
        result = _failed_result(extraction)  # failed before the pipeline ran, e.g. download
    if result is None:
        return "pending"

    # Prefer the DB result, but preserve the legacy MinIO scan preview when its key is present.
    original_url = None
    if study_id and extraction.report_path:
        stored_report = _load_case_report(extraction, study_id)
        if stored_report:
            original_url = stored_report.get("originalUrl")
    return {"originalUrl": original_url, "result": result}


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


def _overview_report(extraction, study_id=None):
    """{source, accepted, lesions} of an approved form, as read by lesion-overview/api.ts."""
    if extraction is None or not extraction.accepted_report:
        return None
    return {
        "source": _report_payload(extraction, study_id),
        "accepted": extraction.accepted_report,
        "lesions": extraction.lesion_answers or {},
    }


def _is_corrected(lesions) -> bool:
    if not isinstance(lesions, dict):
        return False
    return any(
        isinstance(answer, dict) and answer.get("state") == "corrected"
        for fields in lesions.values()
        if isinstance(fields, dict)
        for answer in fields.values()
    )


def _legacy_main_lesion_answers(extraction, lesions):
    """Support the older payload where `lesions` contains answers but no top-level `report`."""
    if not isinstance(lesions, dict) or not lesions:
        return None

    main_lesion = (
        _main_lesion(extraction.generated_report)
        if isinstance(extraction.generated_report, dict)
        else None
    )
    lesion_id = (main_lesion or {}).get("id")

    answers = None
    if lesion_id is not None:
        answers = lesions.get(str(lesion_id))
        if answers is None:
            answers = lesions.get(lesion_id)

    if answers is None:
        answers = next(iter(lesions.values()))
    return answers


def _apply_form(extraction, submitted, user):
    """Store both current and legacy review-form payloads on the extraction."""
    submitted = submitted if isinstance(submitted, dict) else {}
    report = submitted.get("report")
    fields = submitted.get("fields")
    lesions = submitted.get("lesions")
    lesions = lesions if isinstance(lesions, dict) else {}

    if isinstance(report, dict):
        # Current frontend sends the worker report schema and per-lesion field answers separately.
        extraction.accepted_report = report
        extraction.lesion_answers = lesions
    elif isinstance(fields, dict):
        # Older frontend sent normalized form fields in `fields`.
        extraction.accepted_report = _as_fields(fields)
        if isinstance(submitted.get("lesions"), dict):
            extraction.lesion_answers = lesions
    elif lesions:
        # Older frontend may send only lesion answers. Preserve all answers and also populate
        # accepted_report with the main lesion's normalized values for legacy consumers.
        answers = _legacy_main_lesion_answers(extraction, lesions)
        if isinstance(answers, dict):
            extraction.accepted_report = _as_fields(answers)
        elif not extraction.accepted_report:
            extraction.accepted_report = extraction.generated_report
        extraction.lesion_answers = lesions
    elif any(key in submitted for key in REPORT_FIELDS):
        # Also accept the legacy flat payload: {birads, location, size, ...}.
        extraction.accepted_report = _as_fields(submitted)
    elif not extraction.accepted_report:
        # Empty approval means accepting the model proposal without edits.
        extraction.accepted_report = extraction.generated_report

    accepted = _as_fields(extraction.accepted_report)
    generated = _as_fields(extraction.generated_report)
    changed_values = any(
        key in generated and value != generated[key]
        for key, value in accepted.items()
    )

    extraction.status = (
        StatusChoices.CORRECTED
        if _is_corrected(lesions) or changed_values
        else StatusChoices.APPROVED
    )
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
    all_ids = set([item["study_id"] for item in seg_done]).union(
        [item["study_id"] for item in ext_done]
    )
    studies = list(Study.objects.filter(id__in=all_ids))

    if not studies:
        return Response([], status=status.HTTP_200_OK)

    # newest segmentation and active report per study, two queries for all of them
    study_ids = [s.id for s in studies]
    segmentations = {
        s.study_id: s
        for s in SegmentationResult.objects.filter(study_id__in=study_ids).order_by("id")
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
        o_study = next(
            (s for s in o_studies if s.get("orthanc_id") == study.orthanc_path), {}
        )
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

    approved_mask = False
    approved_form = False

    with transaction.atomic():
        segmentation = (
            SegmentationResult.objects.select_for_update()
            .filter(study=study)
            .order_by("-id")
            .first()
        )
        extraction = ExtractionResult.objects.select_for_update().filter(study=study).active()

        if segmentation and segmentation.status in [StatusChoices.COMPLETED, StatusChoices.REJECTED]:
            segmentation.status = new_status
            segmentation.accepted_by = request.user
            segmentation.accepted_at = timezone.now().date()
            segmentation.save()
            approved_mask = True

        # Current behavior: approving the case also accepts the report when it is ready.
        if extraction and extraction.status in [StatusChoices.COMPLETED, StatusChoices.REJECTED]:
            _apply_form(extraction, payload, request.user)
            approved_form = True

    obj_label = f"#{str(study.id).zfill(4)}"
    mask_detail = "corrected" if mask_choice == "corrected" else "no changes"
    if approved_mask:
        record_audit(request, kind="mask_approved", object=obj_label, detail=mask_detail)
    if approved_form:
        record_audit(request, kind="form_approved", object=obj_label, detail="zatwierdzono komplet")

    return Response(status=status.HTTP_200_OK)


@api_view(["POST"])
@require_permission(["review"])
def approve_mask(request, study_id):
    study = get_object_or_404(Study, orthanc_path=study_id)
    payload = request.data
    mask_choice = payload.get("mask", "confirmed")
    new_status = StatusChoices.APPROVED if mask_choice == "confirmed" else StatusChoices.CORRECTED

    approved_mask = False
    with transaction.atomic():
        segmentation = (
            SegmentationResult.objects.select_for_update()
            .filter(study=study)
            .order_by("-id")
            .first()
        )
        if segmentation and segmentation.status in [StatusChoices.COMPLETED, StatusChoices.REJECTED]:
            segmentation.status = new_status
            segmentation.accepted_by = request.user
            segmentation.accepted_at = timezone.now().date()
            segmentation.save()
            approved_mask = True

    if approved_mask:
        obj_label = f"#{str(study.id).zfill(4)}"
        mask_detail = "corrected" if mask_choice == "corrected" else "no changes"
        record_audit(request, kind="mask_approved", object=obj_label, detail=mask_detail)

    return Response(status=status.HTTP_200_OK)


@api_view(["POST"])
@require_permission(["review"])
def reopen_case(request, study_id):
    study = get_object_or_404(Study, orthanc_path=study_id)
    obj_label = f"#{str(study.id).zfill(4)}"

    reopened_mask = False
    reopened_form = False

    with transaction.atomic():
        segmentation = (
            SegmentationResult.objects.select_for_update()
            .filter(study=study)
            .order_by("-id")
            .first()
        )
        if segmentation and segmentation.status in (StatusChoices.APPROVED, StatusChoices.CORRECTED):
            segmentation.status = StatusChoices.COMPLETED
            segmentation.accepted_by = None
            segmentation.accepted_at = None
            segmentation.save()
            reopened_mask = True

        extraction = ExtractionResult.objects.select_for_update().filter(study=study).active()
        if extraction and extraction.status in (StatusChoices.APPROVED, StatusChoices.CORRECTED):
            extraction.status = StatusChoices.COMPLETED
            extraction.accepted_by = None
            extraction.accepted_at = None
            extraction.save()
            reopened_form = True

    if reopened_mask:
        record_audit(request, kind="mask_unapproved", object=obj_label, detail="reopened case")

    if reopened_form:
        record_audit(request, kind="form_unapproved", object=obj_label, detail="reopened case")

    return Response(status=status.HTTP_200_OK)


@api_view(["POST"])
@require_permission(["review"])
def unapprove_mask(request, study_id):
    study = get_object_or_404(Study, orthanc_path=study_id)

    unapproved_mask = False
    with transaction.atomic():
        segmentation = (
            SegmentationResult.objects.select_for_update()
            .filter(study=study)
            .order_by("-id")
            .first()
        )
        if segmentation and segmentation.status in (StatusChoices.APPROVED, StatusChoices.CORRECTED):
            segmentation.status = StatusChoices.COMPLETED
            segmentation.accepted_by = None
            segmentation.accepted_at = None
            segmentation.save()
            unapproved_mask = True

    if unapproved_mask:
        record_audit(
            request,
            kind="mask_unapproved",
            object=f"#{str(study.id).zfill(4)}",
            detail=None,
        )

    return Response(status=status.HTTP_200_OK)


@api_view(["POST"])
@require_permission(["review"])
def approve_form(request, study_id):
    study = get_object_or_404(Study, orthanc_path=study_id)
    submitted = request.data

    approved_form = False
    with transaction.atomic():
        extraction = ExtractionResult.objects.select_for_update().filter(study=study).active()
        if extraction and extraction.status in [StatusChoices.COMPLETED, StatusChoices.REJECTED]:
            _apply_form(extraction, submitted, request.user)
            approved_form = True

    if approved_form:
        record_audit(
            request,
            kind="form_approved",
            object=f"#{str(study.id).zfill(4)}",
            detail="Form approved",
        )

    return Response(status=status.HTTP_200_OK)


@api_view(["POST"])
@require_permission(["review"])
def unapprove_form(request, study_id):
    study = get_object_or_404(Study, orthanc_path=study_id)

    unapproved_form = False
    with transaction.atomic():
        extraction = ExtractionResult.objects.select_for_update().filter(study=study).active()
        if extraction and extraction.status in (StatusChoices.APPROVED, StatusChoices.CORRECTED):
            extraction.status = StatusChoices.COMPLETED
            extraction.accepted_by = None
            extraction.accepted_at = None
            extraction.save()
            unapproved_form = True

    if unapproved_form:
        record_audit(
            request,
            kind="form_unapproved",
            object=f"#{str(study.id).zfill(4)}",
            detail=None,
        )

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
            (s for s in OrthancClient().list_studies() if s.get("orthanc_id") == study.orthanc_path),
            {},
        )
    except OrthancUnavailable:  # includes OrthancUnauthorized
        o_data = {}

    corrected = segmentation.status == StatusChoices.CORRECTED
    saving = corrected and not segmentation.accepted_path
    measured = _mask_measurements(segmentation)

    accepted_or_generated = None
    if extraction:
        accepted_or_generated = extraction.accepted_report or extraction.generated_report
    by_field = _as_fields(accepted_or_generated)

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
        "measurements": {
            "volume": (measured or {}).get("volume_ml"),
            "dimensions": (measured or {}).get("dimensions_mm"),
            "intensity": None,
        },
        "report": _overview_report(extraction, study.orthanc_path),
        "comparison": [
            {
                "feature": "largestSize",
                "fromMask": _largest_mm(measured),
                "fromReport": by_field.get("size"),
                "match": None,
            },
            {
                "feature": "quadrant",
                "fromMask": None,
                "fromReport": by_field.get("location"),
                "match": None,
            },
        ],
        "verification": {
            "by": _user_name(segmentation.accepted_by),
            "date": accepted_at,
            "agreement": None,
            "segmentationVersion": seg_version or "-",
            "extractionVersion": ext_version,
        },
    })