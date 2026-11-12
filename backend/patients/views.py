import io
import logging
import zipfile
from uuid import uuid4
from datetime import timedelta

from django.db.models import Count, Q
from django.utils import timezone
import pydicom
from celery import current_app
from django.core.cache import cache
from django.db import transaction
from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.decorators import api_view, parser_classes, permission_classes
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from common.storage import put_bytes
from extraction.models import ExtractionResult
from extraction.models import StatusChoices as ExtractionStatus
from segmentation.models import SegmentationResult
from users.permissions import require_permission
from audit.utils import record_audit
from .models import Study
from .orthanc_client import OrthancClient, OrthancUnauthorized, OrthancUnavailable

import json
logger = logging.getLogger(__name__)

# The list and the dashboard both ask Orthanc for the same thing; a few seconds of cache is enough.
STUDIES_CACHE_KEY = "orthanc:studies"
STUDIES_CACHE_TTL = 5

SERVER_ERROR = {
    "code": "server_error",
    "detail": "Wystąpił nieoczekiwany błąd serwera.",
}

# What the extraction worker can read (workers/extraction/documents.py); the same list as the
# file picker in the frontend (AttachReport.tsx).
REPORT_SUFFIXES = (".txt", ".jpg", ".jpeg", ".png")


# ---------------------------------------------------------------- helpers

def _orthanc_studies() -> list[dict]:
    studies = cache.get(STUDIES_CACHE_KEY)
    if studies is None:
        studies = OrthancClient().list_studies()
        cache.set(STUDIES_CACHE_KEY, studies, STUDIES_CACHE_TTL)
    return studies


def _orthanc_error_response(exc: OrthancUnavailable) -> Response:
    if isinstance(exc, OrthancUnauthorized):
        return Response(
            {
                "code": "orthanc_unauthorized",
                "detail": "Orthanc (DICOM server) rejected the backend's credentials.",
            },
            status=status.HTTP_503_SERVICE_UNAVAILABLE,
        )
    return Response(
        {
            "code": "orthanc_unavailable",
            "detail": "Orthanc (DICOM server) is unavailable.",
        },
        status=status.HTTP_503_SERVICE_UNAVAILABLE,
    )


def _load_state(orthanc_studies: list[dict]):
    """Three queries in total, no matter how many studies there are.

    The newest extraction/segmentation (highest id) wins when a study has several.
    """
    ids = [s.get("orthanc_id") for s in orthanc_studies]
    db_studies = {s.orthanc_path: s for s in Study.objects.filter(orthanc_path__in=ids)}
    study_ids = [s.id for s in db_studies.values()]
    extractions = {
        e.study_id: e for e in ExtractionResult.objects.filter(study_id__in=study_ids).order_by("id")
    }
    segmentations = {
        s.study_id: s for s in SegmentationResult.objects.filter(study_id__in=study_ids).order_by("id")
    }
    return db_studies, extractions, segmentations


def _pick_uncertainty(segmentation, extraction):
    if segmentation is not None and segmentation.uncertainty is not None:
        return segmentation.uncertainty
    if extraction is not None and extraction.uncertainty is not None:
        return extraction.uncertainty
    return None


def _check_archive(archive_bytes: bytes) -> Response | None:
    """Returns an error response, or None when the archive holds exactly one DICOM study."""
    if not zipfile.is_zipfile(io.BytesIO(archive_bytes)):
        return Response({"detail": "Not correct ZIP file archive."}, status=status.HTTP_400_BAD_REQUEST)

    try:
        with zipfile.ZipFile(io.BytesIO(archive_bytes)) as zf:
            names = [
                n
                for n in zf.namelist()
                if not n.startswith("__MACOSX") and not n.endswith(".DS_Store") and not n.endswith("/")
            ]
            if not names:
                return Response({"detail": "No files in archive."}, status=status.HTTP_400_BAD_REQUEST)

            study_uids: set[str] = set()
            for name in names:
                try:
                    with zf.open(name) as dicom_file:
                        ds = pydicom.dcmread(dicom_file, stop_before_pixels=True, specific_tags=["StudyInstanceUID"])
                    if hasattr(ds, "StudyInstanceUID"):
                        study_uids.add(str(ds.StudyInstanceUID))
                except Exception:
                    continue
                if len(study_uids) > 1:
                    break  # no need to read the rest

            if not study_uids:
                return Response(
                    {"detail": "No valid DICOM metadata found in archive files."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            if len(study_uids) > 1:
                return Response(
                    {
                        "code": "multiple_studies_error",
                        "detail": (
                            "The ZIP archive contains files from multiple different studies "
                            "(different StudyInstanceUID). Please upload one study per archive."
                        ),
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )
    except zipfile.BadZipFile:
        return Response({"detail": "ZIP archive is damaged."}, status=status.HTTP_400_BAD_REQUEST)
    return None

def _verified_stats():
    """Verified cases for today and for each of the last 7 days (one query)."""
    today = timezone.localdate()
    week_start = today - timedelta(days=6)

    rows = (
        SegmentationResult.objects
        .filter(accepted_at__range=(week_start, today), status__in=["APPROVED", "CORRECTED"])
        .order_by()
        .values("accepted_at")
        .annotate(
            unchanged=Count("id", filter=Q(status="APPROVED")),
            corrected=Count("id", filter=Q(status="CORRECTED")),
        )
    )
    by_day = {row["accepted_at"]: row for row in rows}

    last_week = []
    for i in range(7):
        day = week_start + timedelta(days=i)
        row = by_day.get(day)
        last_week.append({
            "date": day.isoformat(),
            "unchanged": row["unchanged"] if row else 0,
            "corrected": row["corrected"] if row else 0,
        })

    today_row = by_day.get(today)
    verified_today = (today_row["unchanged"] + today_row["corrected"]) if today_row else 0
    return verified_today, last_week


def _orthanc_study_id(orthanc_response) -> str | None:
    item = orthanc_response
    if isinstance(item, list):
        item = item[0] if item else None
    if isinstance(item, dict):
        return item.get("ParentStudy") or item.get("ID")
    return str(item) if item else None


def _check_report_file(report_file) -> Response | None:
    """An error response for a report file the extractor cannot read, otherwise None."""
    if report_file.name.lower().endswith(REPORT_SUFFIXES):
        return None
    return Response(
        {
            "code": "unsupported_report_type",
            "detail": f"Nieobsługiwany typ pliku opisu; dozwolone: {', '.join(REPORT_SUFFIXES)}.",
        },
        status=status.HTTP_400_BAD_REQUEST,
    )


def _store_report(report_file, study) -> ExtractionResult:
    """Saves the file, creates the row and schedules extraction once the transaction commits."""
    # uuid folder: two reports with the same file name must not overwrite each other
    key = f"reports/{uuid4().hex}/{report_file.name}"
    put_bytes(report_file.read(), "reports", key, report_file.content_type)
    extraction = ExtractionResult.objects.create(study=study, report_path=key)
    extraction_id = extraction.id
    transaction.on_commit(
        lambda: current_app.send_task("extraction.run", kwargs={"extraction_id": extraction_id, "keys": [key]})
    )
    return extraction


# ---------------------------------------------------------------- views

@api_view(["GET"])
@permission_classes([IsAuthenticated])
def study_list(request):
    try:
        orthanc_studies = _orthanc_studies()
    except OrthancUnavailable as exc:  # includes OrthancUnauthorized
        return _orthanc_error_response(exc)

    db_studies, extractions, segmentations = _load_state(orthanc_studies)

    response_data = []
    for o_study in orthanc_studies:
        orthanc_id = o_study.get("orthanc_id")
        db_study = db_studies.get(orthanc_id)
        if not db_study: continue
        extraction = extractions.get(db_study.id) if db_study else None
        segmentation = segmentations.get(db_study.id) if db_study else None

        response_data.append(
            {
                "orthanc_id": orthanc_id,
                "study_instance_uid": o_study.get("study_instance_uid"),
                "patient_id": o_study.get("patient_id"),
                "study_date": o_study.get("study_date"),
                "description": o_study.get("description"),
                "modalities": o_study.get("modalities", []),
                "series_count": o_study.get("series_count", 0),
                "viewer_url": o_study.get("viewer_url"),
                "extraction_status": extraction.status if extraction else "missing",
                "segmentation_status": segmentation.status if segmentation else "queued",
                "uncertainty": _pick_uncertainty(segmentation, extraction),
            }
        )
    logger.warning(
        "OVERVIEW REPORT: %s",
        json.dumps(response_data, ensure_ascii=False, default=str)
    )

    return Response(response_data)


@api_view(["POST"])
@parser_classes([MultiPartParser, FormParser])
@require_permission("addStudies")
def study_import(request):
    """Accepts a ZIP with one DICOM study and/or a report file (.txt, .jpg, .png)."""
    archive_file = request.FILES.get("archives")
    report_file = request.FILES.get("report")

    if not archive_file and not report_file:
        return Response({"detail": "No files were provided for import."}, status=status.HTTP_400_BAD_REQUEST)
    # before the archive goes to Orthanc, so a bad report leaves nothing behind
    if report_file and (error := _check_report_file(report_file)):
        return error

    archive_bytes = None
    orthanc_study_id = None

    # 1. Validate and push the DICOM archive to Orthanc (outside the DB transaction: it is slow I/O)
    if archive_file:
        archive_bytes = archive_file.read()
        error = _check_archive(archive_bytes)
        if error:
            return error

        try:
            orthanc_study_id = _orthanc_study_id(OrthancClient().upload_dicom_zip(archive_bytes))
        except OrthancUnavailable as exc:
            return _orthanc_error_response(exc)

        if not orthanc_study_id:
            # no guessing "the newest study in the list": that could be somebody else's study
            logger.error("Orthanc accepted the upload but returned no study id")
            return Response(
                {"code": "orthanc_bad_response", "detail": "Orthanc did not return the study id."},
                status=status.HTTP_502_BAD_GATEWAY,
            )

    # 2. Database rows, files and tasks
    try:
        with transaction.atomic():
            study = None
            if orthanc_study_id:
                study, created = Study.objects.get_or_create(orthanc_path=orthanc_study_id)
                if not created:
                    return Response(
                        {"code": "study_already_exists", "detail": "To badanie jest już w systemie."},
                        status=status.HTTP_400_BAD_REQUEST,
                    )
                # stored only after Orthanc accepted it, so a rejected study leaves no orphan in MinIO
                # put_bytes(archive_bytes, "studies", f"ZIP/{archive_file.name}")
                study_pk = study.id
                transaction.on_commit(
                    lambda: current_app.send_task("segmentation.run", kwargs={"study_id": study_pk})
                )

            if report_file:
                # no DICOM in this request: the report stays unassigned (study=None)
                _store_report(report_file, study)
    except Exception:
        logger.exception("Study import failed")
        return Response(SERVER_ERROR, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    cache.delete(STUDIES_CACHE_KEY)  # the new study should show up in the list right away

    study_num_str = f"#{study.id}" if study else "raport"
    record_audit(
        request,
        kind="study_imported",
        object=study_num_str,
        detail=f"Zaimportowano badanie z Orthanc ID: {orthanc_study_id}" if orthanc_study_id else "Zaimportowano sam raport"
    )

    return Response(
        {
            "detail": "Study and documents have been successfully imported.",
            "study_id": study.id if study else None,
            "orthanc_path": orthanc_study_id,
        },
        status=status.HTTP_201_CREATED,
    )


@api_view(["POST"])
@parser_classes([MultiPartParser, FormParser])
@require_permission("addStudies")
def attach_report_to_study(request, orthanc_id):
    """Attaches a new report file to an existing study (looked up by orthanc_path)."""
    study = get_object_or_404(Study, orthanc_path=orthanc_id)
    report_file = request.FILES.get("report")
    if not report_file:
        return Response({"detail": "No report file provided."}, status=status.HTTP_400_BAD_REQUEST)
    if error := _check_report_file(report_file):
        return error

    try:
        with transaction.atomic():
            _store_report(report_file, study)
    except Exception:
        logger.exception("Attaching report failed")
        return Response(SERVER_ERROR, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    
    record_audit(
        request,
        kind="attach_report",
        object=str(orthanc_id),
        detail=f"Dołączono nowy plik raportu: {report_file.name}"
    )
    return Response({"detail": "Report successfully attached to the study."}, status=status.HTTP_200_OK)


@api_view(["POST"])
@require_permission("addStudies")
def attach_existing_report(request, orthanc_id):
    """Assigns an already uploaded, unassigned report to a study."""
    study = get_object_or_404(Study, orthanc_path=orthanc_id)
    report_id = request.data.get("report_id")
    if not report_id:
        return Response({"detail": "No report_id provided."}, status=status.HTTP_400_BAD_REQUEST)


    updated = ExtractionResult.objects.filter(id=report_id, study__isnull=True).update(study=study)
    if not updated:
        return Response({"detail": "Report not found or already assigned."}, status=status.HTTP_404_NOT_FOUND)
    
    record_audit(
            request,
            kind="attach_report",
            object=str(orthanc_id),
            detail=f"Dołączono nowy plik raportu: {report_id}"
    )

    return Response({"detail": "Existing report successfully attached to the study."}, status=status.HTTP_200_OK)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def unassigned_reports_list(request):
    response_data = []
    for item in ExtractionResult.objects.filter(study__isnull=True).order_by("-id"):
        file_name = item.report_path.split("/")[-1] if item.report_path else "unknown"
        ext = file_name.rsplit(".", 1)[-1].lower()
        kind = "scan" if ext in ("jpg", "jpeg", "png") else "text"
        created_at = item.created_at

        response_data.append(
            {
                "id": str(item.id),
                "fileName": file_name,
                "kind": kind,
                "addedAt": created_at.strftime("%Y-%m-%d") if created_at else None,
                # these reports are not on the dashboard, so a failed extraction shows only here
                "status": item.status,
                "error": item.error if item.status == ExtractionStatus.FAILED else "",
            }
        )

    return Response(response_data, status=status.HTTP_200_OK)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def dashboard_view(request):
    try:
        orthanc_studies = _orthanc_studies()
    except OrthancUnavailable:  # includes OrthancUnauthorized
        orthanc_studies = []

    db_studies, extractions, segmentations = _load_state(orthanc_studies)

    queue_items = []
    in_progress_items = []
    processing_count = 0
    to_review_count = 0
    missing_reports_count = 0
    failed_studies = []
    for idx, o_study in enumerate(orthanc_studies):
        db_study = db_studies.get(o_study.get("orthanc_id"))
        if not db_study: continue
        extraction = extractions.get(db_study.id) if db_study else None
        segmentation = segmentations.get(db_study.id) if db_study else None

        missing_reports_count += 1 if not extraction else 0
        
        seg_status = segmentation.status if segmentation else "COMPLETED"
        ext_status = extraction.status if extraction else "COMPLETED"

        uncertainty = _pick_uncertainty(segmentation, extraction)
        if uncertainty is None:
            uncertainty = 0.5

        study_number = str(idx + 1).zfill(4)
        if ext_status == ExtractionStatus.FAILED:
            failed_studies.append(study_number)

        if seg_status in ("PROCESSING", "PENDING") or ext_status in ("PROCESSING", "PENDING"):
            processing_count += 1
            if len(in_progress_items) < 5:
                in_progress_items.append(
                    {
                        "studyNumber": study_number,
                        "stage": "segmentation" if seg_status == "PROCESSING" else "extraction",
                        "state": "running" if "PROCESSING" in (seg_status, ext_status) else "queued",
                    }
                )
        elif (seg_status == "COMPLETED" and segmentation) or (ext_status == "COMPLETED" and extraction):
            to_review_count += 1
            queue_items.append(
                {
                    "studyId": str(db_study.id) if db_study else f"s{idx + 1}",
                    "studyNumber": study_number,
                    "patientId": o_study.get("patient_id") or "---",
                    "studyDate": o_study.get("study_date") or "----------",
                    "uncertainty": float(uncertainty),
                }
            )


    attention_items = [
        {"kind": "processing_error", "subject": number, "href": "/badania"}
        for number in failed_studies
    ]
    if missing_reports_count > 0:
        attention_items.append(
            {"kind": "missing_report", "subject": "", "count": missing_reports_count, "href": "/badania"}
        )
    verified_today, verified_last_week = _verified_stats()
    return Response(
        {
            "toReview": to_review_count or len(queue_items),
            "processing": processing_count,
            "verifiedToday": verified_today,
            "queue": queue_items,
            "attention": attention_items,
            "inProgress": in_progress_items,
            "verifiedLastWeek": verified_last_week,
        },
        status=status.HTTP_200_OK,
    )