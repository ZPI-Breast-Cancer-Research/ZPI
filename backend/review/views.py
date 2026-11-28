import logging
import mimetypes

from audit.utils import record_audit
from common.errors import ObjectNotFound
from common.storage import BUCKET_REPORTS, get_bytes
from django.db import transaction
from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from django.urls import reverse
from django.utils import timezone
from extraction.models import ExtractionResult, SourceChoices, StatusChoices
from patients.errors import OrthancUnauthorized, OrthancUnavailable
from patients.models import Study
from patients.orthanc_client import OrthancClient
from rest_framework import status
from rest_framework.decorators import api_view
from rest_framework.response import Response
from segmentation.approval import approve_corrected_seg, approve_mask_in_case, reopen_mask
from segmentation.approval import approve_mask as approve_segmentation_mask
from segmentation.models import SegmentationResult
from users.permissions import require_permission

logger = logging.getLogger(__name__)

VERIFIED = (StatusChoices.APPROVED, StatusChoices.CORRECTED)
REPORT_FIELDS = [
    "birads",
    "location",
    "size",
    "shape",
    "margin",
    "curve",
]  # = FieldKey on the frontend
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


def _model_version(result) -> str | None:
    """Version of the model that produced a result; None without a result or a model."""
    model = result.model if result else None
    return model.version if model else None


def _uncertainty(segmentation, extraction) -> float | None:
    # a finished mask without uncertainty (empty map, failed entropy) is unknown, not certain:
    # falling back to the report's value would push it down the queue
    if (
        segmentation is not None
        and segmentation.status == StatusChoices.COMPLETED
        and segmentation.uncertainty is None
    ):
        return None
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
    """The lesion with the highest BI-RADS (first one on ties).

    TODO: pick the one that matches the mask.
    """
    lesions = report.get("zmiany") or []
    if not lesions:
        return None

    def rank(lesion):
        birads = str(lesion.get("birads") or "").lower()
        return BIRADS_ORDER.index(birads) if birads in BIRADS_ORDER else -1

    return max(lesions, key=rank)


def _correction_saving(segmentation) -> bool:
    """A corrected mask the worker has not converted yet (ADR 0004).

    Until then ``measurements`` still hold the numbers of the model's mask; the worker replaces
    them with the corrected mask's when it sets ``accepted_path``.
    """
    return segmentation.status == StatusChoices.CORRECTED and not segmentation.accepted_path


def _mask_measurements(segmentation) -> dict | None:
    """Measurements of the mask on screen; none while a correction is still being saved."""
    if segmentation is None or _correction_saving(segmentation):
        return None
    return segmentation.measurements


def _overview_measurements(segmentation) -> dict | None:
    """What the overview shows as "Pomiary z segmentacji" (frontend/src/lesion-overview/api.ts).

    The worker measures the model's mask, and a corrected one once it has converted it. While a
    correction is being saved the model's numbers stand in and say so.
    """
    measured = (segmentation.measurements if segmentation else None) or {}
    size = _largest_mm(measured)
    if size is None or measured.get("volume_ml") is None:
        return None
    total = measured["volume_ml"]
    return {
        "source": "model" if _correction_saving(segmentation) else "approved",
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
    obs = next(
        (o for o in observations if o.get("wymiary")), observations[0] if observations else None
    )
    if obs:
        if obs.get("lokalizacje"):
            fields["location"] = _ui_value("location", obs["lokalizacje"][0])
        if size := _size_value(obs.get("wymiary")):
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


# the worker has not finished a run of the report yet
WAITING = (StatusChoices.UPLOADED, StatusChoices.PENDING, StatusChoices.PROCESSING)


def _report_payload(extraction, study_id):
    """What the review screens show as the report (frontend/src/review/extraction.ts CaseReport).

    {"originalUrl", "result"} once the worker has a result; "pending" while it has none yet, which
    the frontend shows as waiting; None without a report. The result is put together from the
    columns of the report row in the shape of the worker's ExtractionResult.
    """
    if extraction is None:
        return None
    if extraction.source == SourceChoices.MANUAL:
        return {"originalUrl": None, "result": _manual_result(extraction)}
    if extraction.status in WAITING:
        return "pending"
    url = reverse("review-report-scan", args=[study_id]) if extraction.report_path else None
    return {"originalUrl": url, "result": _worker_result(extraction)}


def _worker_result(extraction) -> dict:
    failed = extraction.status == StatusChoices.FAILED
    return _result_shape(
        extraction,
        outcome="error" if failed else "ok",
        data=None if failed else extraction.generated_report,
        error=extraction.error,
        source=(extraction.report_path or "").rsplit("/", 1)[-1],
    )


def _manual_result(extraction) -> dict:
    """A form filled in by the radiologist, in the shape of a worker result (no file, no text)."""
    return _result_shape(
        extraction, outcome="ok", data=extraction.accepted_report, error=None, source="manual"
    )


def _result_shape(extraction, *, outcome, data, error, source) -> dict:
    """The worker's ExtractionResult (workers/extraction/schema.py) from the report columns."""
    ocr = extraction.ocr_model
    ocr_settings = (ocr.ocr_settings or {}) if ocr else {}
    model = extraction.model
    return {
        "source": source,
        "status": outcome,
        "data": data,
        "error": (error or "unknown error") if outcome == "error" else None,
        "failedStep": extraction.failed_step or None,
        "warnings": extraction.warnings or [],
        "text": extraction.ocr_text or "",
        "provenance": {
            "ocr_engine": ocr.ocr_engine if ocr else None,
            "ocr_engine_version": extraction.ocr_engine_version or None,
            "ocr_mean_confidence": extraction.ocr_confidence,
            "orientation_detector": ocr_settings.get("orientation"),
            "page_rotations": extraction.page_rotations or [],
            # the LLM and the prompt belong to the extraction version the report was run with
            "llm_provider": "",
            "llm_model": model.llm_model if model else "",
            "prompt_version": model.prompt_version if model else "",
            "schema_version": extraction.schema_version or "",
        },
        "attempts": extraction.attempts or 0,
        "ocr_seconds": extraction.ocr_seconds,
        "llm_seconds": extraction.llm_seconds,
        "created_at": extraction.updated_at.isoformat() if extraction.updated_at else "",
    }


def _overview_report(extraction, study_id):
    """{source, accepted} of an approved form, as frontend/src/lesion-overview/api.ts reads it."""
    if extraction is None or not extraction.accepted_report:
        return None
    return {
        "source": _report_payload(extraction, study_id),
        "accepted": extraction.accepted_report,
    }


def _is_corrected(field_checks) -> bool:
    """The radiologist changed at least one field of the form."""
    return isinstance(field_checks, dict) and any(
        check == "corrected" for check in field_checks.values()
    )


def _apply_form(extraction, submitted, user):
    """Store the review form: {"report": <worker schema>,
    "fields": {path in the report: "confirmed" | "corrected" | "unverified"}}.

    Without a report the doctor accepts the model's report as it is, or keeps the form accepted
    before together with its checks. Sent again, a report replaces the last answers.
    """
    submitted = submitted if isinstance(submitted, dict) else {}
    report = submitted.get("report")
    field_checks = submitted.get("fields")
    field_checks = field_checks if isinstance(field_checks, dict) else None
    if isinstance(report, dict):
        extraction.accepted_report = report
        extraction.field_checks = field_checks
    elif not extraction.accepted_report:
        extraction.accepted_report = extraction.generated_report
    # the checks stored with the accepted report, not only the ones in this request;
    # a manual form has no model answer to correct
    corrected = extraction.source != SourceChoices.MANUAL and _is_corrected(extraction.field_checks)
    extraction.status = StatusChoices.CORRECTED if corrected else StatusChoices.APPROVED
    extraction.accepted_by = user
    extraction.accepted_at = timezone.now().date()
    extraction.save()


def _manual_report(study, submitted, user):
    """A study without a report gets the form filled in by the radiologist (source = manual).

    None when the request carries no form. The caller holds the lock on the study.
    """
    report = submitted.get("report") if isinstance(submitted, dict) else None
    if not isinstance(report, dict):
        return None
    fields = submitted.get("fields")
    now = timezone.now()
    return ExtractionResult.objects.create(
        study=study,
        source=SourceChoices.MANUAL,
        status=StatusChoices.APPROVED,
        accepted_report=report,
        field_checks=fields if isinstance(fields, dict) else None,
        accepted_by=user,
        accepted_at=now.date(),
        requested_by=user,
        assigned_at=now,
    )


def _audit_object(study) -> str:
    return f"#{str(study.id).zfill(4)}"


def _mask_detail(mask_choice) -> str:
    return "corrected" if mask_choice == "corrected" else "no changes"


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
    """The uploaded original of the active report (image or .txt).

    Shown as a preview next to the form.
    """
    study = get_object_or_404(Study, orthanc_path=study_id)
    extraction = study.extractions.active()
    if not extraction or not extraction.report_path:
        return Response({"detail": "Brak skanu."}, status=status.HTTP_404_NOT_FOUND)
    try:
        data = get_bytes(BUCKET_REPORTS, extraction.report_path)
    except ObjectNotFound:
        # the row points at a file that is gone; an unreachable storage is reported as such
        logger.error("Report scan of study %s is missing: %s", study.id, extraction.report_path)
        return Response({"detail": "Brak skanu."}, status=status.HTTP_404_NOT_FOUND)
    content_type = mimetypes.guess_type(extraction.report_path)[0] or "application/octet-stream"
    return HttpResponse(data, content_type=content_type)


@api_view(["GET"])
@require_permission("review")
def review_queue(request):
    """Studies waiting for review: at least one automatic step is COMPLETED, least certain first."""
    # prefilter in the database: only studies that have something COMPLETED
    seg_done = SegmentationResult.objects.filter(status=StatusChoices.COMPLETED).values("study_id")
    ext_done = ExtractionResult.objects.filter(status=StatusChoices.COMPLETED).values("study_id")
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

        queue_data.append(
            {
                "studyId": study.orthanc_path,
                "studyNumber": str(study.id).zfill(4),
                "studyDate": _dicom_date(orthanc_map.get(study.orthanc_path, {}).get("study_date")),
                "uncertainty": _uncertainty(segmentation, extraction),
            }
        )

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
        "segmentationVersion": _model_version(segmentation) or "-",
        "extractionVersion": _model_version(extraction),
        "studyUid": o_study.get("study_instance_uid"),
        # null while there is no SEG: still processing, rejected, or the model found nothing
        "mask": _model_seg(segmentation, o_study.get("study_instance_uid")),
        "report": _report_payload(extraction, study.orthanc_path),
        "proposals": proposals,
        "measurements": {
            "volume": (measured or {}).get("volume_ml"),
            "size": _largest_mm(measured),
            "sizeInReport": _report_size_mm(
                extraction.accepted_report
                if extraction and extraction.source == SourceChoices.MANUAL
                else (extraction.generated_report if extraction else None)
            ),
        },
        "maskApproved": mask_approved_val,
        # scan, text or manual (filled in by the radiologist); None without a report
        "reportSource": extraction.source if extraction else None,
    }

    return Response(case_data, status=status.HTTP_200_OK)


@api_view(["POST"])
@require_permission(["review"])
def approve_case(request, study_id):
    study = get_object_or_404(Study, orthanc_path=study_id)
    payload = request.data
    mask_choice = payload.get("mask", "confirmed")

    with transaction.atomic():
        segmentation = (
            SegmentationResult.objects.select_for_update()
            .filter(study=study)
            .order_by("-id")
            .first()
        )
        Study.objects.select_for_update().get(pk=study.pk)  # one manual form at a time
        extraction = ExtractionResult.objects.select_for_update().filter(study=study).active()

        approved_mask = approve_mask_in_case(
            segmentation, request.user, corrected=mask_choice == "corrected"
        )
        approved_form = bool(extraction) and extraction.status in [
            StatusChoices.COMPLETED,
            StatusChoices.REJECTED,
        ]
        if approved_form:
            _apply_form(extraction, payload, request.user)
        elif extraction is None:
            approved_form = _manual_report(study, payload, request.user) is not None

        if approved_mask:
            record_audit(
                request,
                kind="mask_approved",
                object=_audit_object(study),
                detail=_mask_detail(mask_choice),
            )
        if approved_form:
            record_audit(
                request,
                kind="form_approved",
                object=_audit_object(study),
                detail="zatwierdzono komplet",
            )
    return Response(status=status.HTTP_200_OK)


@api_view(["POST"])
@require_permission(["review"])
def approve_mask(request, study_id):
    """Approve the mask: JSON {mask}, or multipart with the corrected mask as DICOM SEG ("seg")."""
    study = get_object_or_404(Study, orthanc_path=study_id)
    payload = request.data
    seg_file = request.FILES.get("seg")
    mask_choice = "corrected" if seg_file else payload.get("mask", "confirmed")

    with transaction.atomic():
        if seg_file:
            approve_corrected_seg(study, request.user, seg_file.read())
        else:
            segmentation = (
                SegmentationResult.objects.select_for_update()
                .filter(study=study)
                .order_by("-id")
                .first()
            )
            approve_segmentation_mask(
                segmentation, request.user, corrected=mask_choice == "corrected"
            )

        record_audit(
            request,
            kind="mask_approved",
            object=_audit_object(study),
            detail=_mask_detail(mask_choice),
        )
    return Response(status=status.HTTP_200_OK)


@api_view(["POST"])
@require_permission(["review"])
def reopen_case(request, study_id):
    study = get_object_or_404(Study, orthanc_path=study_id)

    with transaction.atomic():
        segmentation = (
            SegmentationResult.objects.select_for_update()
            .filter(study=study)
            .order_by("-id")
            .first()
        )
        reopened_mask = reopen_mask(segmentation)
        extraction = ExtractionResult.objects.select_for_update().filter(study=study).active()
        reopened_form = _reopen(extraction)

        if reopened_mask:
            record_audit(
                request, kind="mask_unapproved", object=_audit_object(study), detail="reopened case"
            )
        if reopened_form:
            record_audit(
                request, kind="form_unapproved", object=_audit_object(study), detail="reopened case"
            )
    return Response(status=status.HTTP_200_OK)


@api_view(["POST"])
@require_permission(["review"])
def unapprove_mask(request, study_id):
    study = get_object_or_404(Study, orthanc_path=study_id)

    with transaction.atomic():
        segmentation = (
            SegmentationResult.objects.select_for_update()
            .filter(study=study)
            .order_by("-id")
            .first()
        )
        unapproved = reopen_mask(segmentation)

        if unapproved:
            record_audit(request, kind="mask_unapproved", object=_audit_object(study))
    return Response(status=status.HTTP_200_OK)


@api_view(["POST"])
@require_permission(["review"])
def approve_form(request, study_id):
    study = get_object_or_404(Study, orthanc_path=study_id)
    submitted = request.data

    with transaction.atomic():
        Study.objects.select_for_update().get(pk=study.pk)  # one manual form at a time
        extraction = ExtractionResult.objects.select_for_update().filter(study=study).active()
        # sent again after a later change
        updated = bool(extraction) and extraction.status in VERIFIED
        waiting = bool(extraction) and extraction.status in (
            StatusChoices.COMPLETED,
            StatusChoices.REJECTED,
        )
        manual = False
        if updated or waiting:
            _apply_form(extraction, submitted, request.user)
        elif extraction is None:
            manual = _manual_report(study, submitted, request.user) is not None
        approved = updated or waiting or manual

    if approved:
        detail = (
            "Form filled in by hand" if manual else "Form updated" if updated else "Form approved"
        )
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

    segmentation = (
        SegmentationResult.objects.select_related("accepted_by").filter(study=study).first()
    )
    extraction = study.extractions.select_related("accepted_by").active()

    if segmentation is None or segmentation.status not in VERIFIED:
        return Response(
            {"code": "not_verified", "detail": "Badanie nie zostało jeszcze zweryfikowane."},
            status=status.HTTP_409_CONFLICT,
        )
    try:
        o_data = next(
            (
                s
                for s in OrthancClient().list_studies()
                if s.get("orthanc_id") == study.orthanc_path
            ),
            {},
        )
    except OrthancUnavailable:  # includes OrthancUnauthorized
        o_data = {}

    corrected = segmentation.status == StatusChoices.CORRECTED
    saving = _correction_saving(segmentation)

    measured = _mask_measurements(segmentation)
    by_field = {row["field"]: row["value"] for row in _report_rows(extraction) or []}

    seg_version = _model_version(segmentation)
    ext_version = _model_version(extraction)
    accepted_at = segmentation.accepted_at.isoformat() if segmentation.accepted_at else ""

    return Response(
        {
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
                "editingSeconds": None,  # no such field in the models yet
                "segmentationVersion": seg_version,
                "extractionVersion": ext_version,
            },
        }
    )
