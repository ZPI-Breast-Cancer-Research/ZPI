from django.utils import timezone
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from django.shortcuts import get_object_or_404
from django.db import transaction
from django.http import HttpResponse
from django.urls import reverse
import mimetypes

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


def _scan_key(extraction) -> str | None:
    """report_path to klucz oryginału w MinIO (obraz lub .txt)."""
    return extraction.report_path if extraction and extraction.report_path else None


def _case_report(extraction, study_id):
    if extraction is None:
        return None
    url = reverse("review-report-scan", args=[study_id]) if _scan_key(extraction) else None
    result = extraction.result
    if isinstance(result, dict) and result.get("provenance"):
        return {"result": result, "originalUrl": url}
    return None

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

def _lesion_fields(lesion: dict, conclusion: dict | None) -> dict:
    """Jedna zmiana -> wartości formularza."""
    fields = {}
    birads = (lesion or {}).get("birads") or (conclusion or {}).get("birads")
    if birads:
        fields["birads"] = str(birads).upper()

    observations = (lesion or {}).get("obserwacje") or []
    if not observations:
        return fields
    obs = next((o for o in observations if o.get("wymiary")), observations[0])

    if locations := obs.get("lokalizacje"):
        fields["location"] = _ui_value("location", locations[0])
    if (size := _size_value(obs.get("wymiary"))) is not None:
        fields["size"] = size
    if obs.get("ksztalt"):
        fields["shape"] = _ui_value("shape", obs["ksztalt"])
    if obs.get("brzeg"):
        fields["margin"] = _ui_value("margin", obs["brzeg"])
    return fields


def _fields_by_lesion(report) -> dict[str, dict]:
    """{"1": {...}, "2": {...}} z polskiego schematu (generated_report)."""
    report = _unwrap_extraction(report)
    conclusion = report.get("wniosek")
    return {
        str(lesion.get("id", i)): _lesion_fields(lesion, conclusion)
        for i, lesion in enumerate(report.get("zmiany") or [], start=1)
    }


def _fields_from_schema(report: dict) -> dict:
    report = _unwrap_extraction(report)
    return _lesion_fields(_main_lesion(report), report.get("wniosek"))


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



@api_view(["GET"])
@require_permission("review")
def report_scan(request, study_id):
    study = get_object_or_404(Study, orthanc_path=study_id)
    extraction = study.extractions.order_by("-id").first()
    key = _scan_key(extraction)
    
    if not key:
        return Response({"detail": "Brak skanu."}, status=status.HTTP_404_NOT_FOUND)
        
    try:
        data = get_bytes(BUCKET_REPORTS, key)
    except Exception:
        logger.exception("Nie udało się wczytać skanu badania %s", study_id)
        return Response({"detail": "Brak skanu."}, status=status.HTTP_404_NOT_FOUND)
        
    content_type = mimetypes.guess_type(key)[0] or "application/octet-stream"
    return HttpResponse(data, content_type=content_type)


def _answers(extraction) -> dict:
    """FieldAnswers: {field: {"value", "state"}}; 'corrected' gdy różni się od propozycji LLM."""
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


def _accepted_lesions(extraction) -> dict[str, dict]:
    accepted = extraction.accepted_report
    if isinstance(accepted, dict) and isinstance(accepted.get("lesions"), dict):
        return accepted["lesions"]
    # legacy: płaski słownik = główna zmiana
    main = _main_lesion(extraction.generated_report) or {}
    flat = _as_fields(accepted)
    generated = _as_fields(extraction.generated_report)
    return {
        str(main.get("id", 1)): {
            k: {"value": v, "state": "confirmed" if generated.get(k) == v else "corrected"}
            for k, v in flat.items()
        }
    }


def _overview_report(extraction, study_id):
    if extraction is None or not extraction.accepted_report:
        return None
    accepted = extraction.accepted_report
    return {
        "source": _case_report(extraction, study_id),
        "accepted": accepted.get("report") if "lesions" in accepted else None,
        "lesions": _accepted_lesions(extraction),
    }

def _normalize_answers(answers, generated: dict) -> dict:
    out = {}
    for key in REPORT_FIELDS:
        raw = (answers or {}).get(key)
        value = raw.get("value") if isinstance(raw, dict) else raw
        if value is None:
            continue
        value = str(value).upper() if key == "birads" else _ui_value(key, value)
        state = raw.get("state") if isinstance(raw, dict) else None
        if state == "confirmed" and generated.get(key) != value:
            state = "corrected"
        if state not in ("confirmed", "corrected"):
            state = "confirmed" if generated.get(key) == value else "corrected"
        out[key] = {"value": str(value), "state": state}
    return out


def _apply_form(extraction, submitted, user):
    submitted = submitted if isinstance(submitted, dict) else {}
    generated = _fields_by_lesion(extraction.generated_report)

    raw_lesions = submitted.get("lesions")
    if not isinstance(raw_lesions, dict) or not raw_lesions:
        # stary kształt: płaskie "fields" -> główna zmiana
        main = _main_lesion(extraction.generated_report) or {}
        raw_lesions = {str(main.get("id", 1)): submitted.get("fields") or {}}

    lesions = {
        str(lid): _normalize_answers(answers, generated.get(str(lid), {}))
        for lid, answers in raw_lesions.items()
    }

    extraction.accepted_report = {"report": submitted.get("report"), "lesions": lesions}
    corrected = any(
        a["state"] == "corrected" for answers in lesions.values() for a in answers.values()
    )
    extraction.status = StatusChoices.CORRECTED if corrected else StatusChoices.APPROVED
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

    # newest result per study, two queries for all of them
    study_ids = [s.id for s in studies]
    segmentations = {
        s.study_id: s for s in SegmentationResult.objects.filter(study_id__in=study_ids).order_by("id")
    }
    extractions = {
        e.study_id: e for e in ExtractionResult.objects.filter(study_id__in=study_ids).order_by("id")
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

        # the prefilter looked at any result; here we check the newest one
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
    extraction = ExtractionResult.objects.filter(study=study).order_by("-id").first()
    if extraction:
        generated = extraction.generated_report

        logger.warning(
            "GENERATED_REPORT dla study #%s:\n%s",
            study.id,
            json.dumps(
                generated,
                ensure_ascii=False,
                indent=2,
                default=str,
            ),
        )

        unwrapped = _unwrap_extraction(generated)
        lesions = unwrapped.get("zmiany") or []

        logger.warning(
            "GENERATED_REPORT SUMMARY | study=%s | lesions_count=%s | lesion_ids=%s",
            study.id,
            len(lesions),
            [lesion.get("id") for lesion in lesions],
        )
    else:
        logger.warning(
            "BRAK EXTRACTION dla study #%s",
            study.id,
        )
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

        proposals["lesions"] = {
            lesion_id: {
                key: {"value": value}
                for key, value in fields.items()
            }
            for lesion_id, fields in _fields_by_lesion(
                extraction.generated_report
            ).items()
        }

    report = _case_report(extraction, study.orthanc_path)

    if (
        report is None
        and extraction
        and extraction.status in (StatusChoices.PENDING, StatusChoices.PROCESSING)
    ):
        report = {"pending": True}

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
        "mask": _model_seg(segmentation, o_study.get("study_instance_uid")),
        "report": report,
        "segmentation": {"series": None} if segmentation else None,
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

    approved_mask = False
    approved_form = False

    with transaction.atomic():
        segmentation = SegmentationResult.objects.select_for_update().filter(study=study).order_by("-id").first()
        extraction = ExtractionResult.objects.select_for_update().filter(study=study).order_by("-id").first()

        if segmentation and segmentation.status in [StatusChoices.COMPLETED, StatusChoices.REJECTED]:
            segmentation.status = new_status
            segmentation.accepted_by = request.user
            segmentation.accepted_at = timezone.now().date()
            segmentation.save()
            approved_mask = True

        if (
            extraction
            and extraction.status in [StatusChoices.COMPLETED, StatusChoices.REJECTED]
            and any(key in payload for key in ("report", "lesions", "fields"))
        ):
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
        segmentation = SegmentationResult.objects.select_for_update().filter(study=study).order_by("-id").first()
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
        segmentation = SegmentationResult.objects.select_for_update().filter(study=study).order_by("-id").first()
        if segmentation and segmentation.status in (StatusChoices.APPROVED, StatusChoices.CORRECTED):
            segmentation.status = StatusChoices.COMPLETED
            segmentation.accepted_by = None
            segmentation.accepted_at = None
            segmentation.save()
            reopened_mask = True

        extraction = ExtractionResult.objects.select_for_update().filter(study=study).order_by("-id").first()
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
        segmentation = SegmentationResult.objects.select_for_update().filter(study=study).order_by("-id").first()
        if segmentation and segmentation.status in (StatusChoices.APPROVED, StatusChoices.CORRECTED):
            segmentation.status = StatusChoices.COMPLETED
            segmentation.accepted_by = None
            segmentation.accepted_at = None
            segmentation.save()
            unapproved_mask = True

    if unapproved_mask:
        record_audit(request, kind="mask_unapproved", object=f"#{str(study.id).zfill(4)}", detail=None)

    return Response(status=status.HTTP_200_OK)


@api_view(["POST"])
@require_permission(["review"])
def approve_form(request, study_id):
    study = get_object_or_404(Study, orthanc_path=study_id)
    submitted = request.data

    approved_form = False
    with transaction.atomic():
        extraction = ExtractionResult.objects.select_for_update().filter(study=study).order_by("-id").first()
        if extraction and extraction.status in [StatusChoices.COMPLETED, StatusChoices.REJECTED]:
            _apply_form(extraction, submitted, request.user)
            approved_form = True

    if approved_form:
        record_audit(request, kind="form_approved", object=f"#{str(study.id).zfill(4)}", detail="Form approved")

    return Response(status=status.HTTP_200_OK)


@api_view(["POST"])
@require_permission(["review"])
def unapprove_form(request, study_id):
    study = get_object_or_404(Study, orthanc_path=study_id)

    unapproved_form = False
    with transaction.atomic():
        extraction = ExtractionResult.objects.select_for_update().filter(study=study).order_by("-id").first()
        if extraction and extraction.status in (StatusChoices.APPROVED, StatusChoices.CORRECTED):
            extraction.status = StatusChoices.COMPLETED
            extraction.accepted_by = None
            extraction.accepted_at = None
            extraction.save()
            unapproved_form = True

    if unapproved_form:
        record_audit(request, kind="form_unapproved", object=f"#{str(study.id).zfill(4)}", detail=None)

    return Response(status=status.HTTP_200_OK)


@api_view(["GET"])
@require_permission("review")
def review_overview(request, study_id):
    """Summary of a verified case; study_id is the Orthanc id, like in review_queue."""
    study = get_object_or_404(Study, orthanc_path=study_id)

    segmentation = study.segmentations.select_related("accepted_by").order_by("-id").first()
    extraction = study.extractions.select_related("accepted_by").order_by("-id").first()

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

    lesions = _accepted_lesions(extraction) if extraction and extraction.accepted_report else {}
    report = _overview_report(extraction, study.orthanc_path)
    main_id = str((_main_lesion(extraction.generated_report) or {}).get("id", 1)) if extraction else None
    by_field = {k: v["value"] for k, v in lesions.get(main_id, {}).items()}
    measured = _mask_measurements(segmentation)
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
        "report": report,
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