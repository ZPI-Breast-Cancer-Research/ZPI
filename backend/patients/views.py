from rest_framework import status
from rest_framework.decorators import api_view, parser_classes, permission_classes
from rest_framework.parsers import MultiPartParser, FormParser
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated

from django.shortcuts import get_object_or_404
from .orthanc_client import OrthancClient, OrthancUnauthorized, OrthancUnavailable
from .models import Study 
from common.storage import put_bytes
from extraction.models import ExtractionResult
import zipfile
import io
import pydicom
from celery import current_app
from users.permissions import require_permission

from extraction.models import ExtractionResult
from segmentation.models import SegmentationResult 

@api_view(["GET"])
@permission_classes([IsAuthenticated])
def study_list(request):
    try:
        orthanc_client = OrthancClient()
        orthanc_studies = orthanc_client.list_studies()
    except OrthancUnauthorized:
        return Response(
            {
                "code": "orthanc_unauthorized",
                "detail": "Orthanc (DICOM server) rejected the backend's credentials.",
            },
            status=status.HTTP_503_SERVICE_UNAVAILABLE,
        )
    except OrthancUnavailable:
        return Response(
            {
                "code": "orthanc_unavailable",
                "detail": "Orthanc (DICOM server) is unavailable.",
            },
            status=status.HTTP_503_SERVICE_UNAVAILABLE,
        )

    response_data = []
    for o_study in orthanc_studies:
        orthanc_id = o_study.get("orthanc_id")
        
        db_study = Study.objects.filter(orthanc_path=orthanc_id).first()
        
        extraction = None
        segmentation = None
        if db_study:
            extraction = ExtractionResult.objects.filter(study=db_study).first()
            segmentation = SegmentationResult.objects.filter(study=db_study).first()

        response_data.append({
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
            "uncertainty": segmentation.uncertainty if segmentation and segmentation.uncertainty else (extraction.uncertainty if extraction else None),
        })

    return Response(response_data)


@api_view(["POST"])
@require_permission(["addStudies"])
@parser_classes([MultiPartParser, FormParser])
def study_import(request):
    """
    Endpoint accepting DICOM files (or a ZIP archive) and an optional report file (.txt, .jpg, .png).
    """
    # 1. Receive files uploaded from the frontend
    archive_file = request.FILES.get("archives")
    report_file = request.FILES.get("report")

    # Validation: did the user provide any files?
    if not archive_file and not report_file:
        return Response(
            {"detail": "No files were provided for import."},
            status=status.HTTP_400_BAD_REQUEST
        )

    study = None
    orthanc_study_id = None

    try:
        # 2. If DICOM files are present, send them to Orthanc
        if archive_file:
            # Wczytujemy bajty raz do pamięci, żeby uniknąć problemów ze wskaźnikiem pliku
            archive_bytes = archive_file.read()

            if not zipfile.is_zipfile(io.BytesIO(archive_bytes)):
                return Response(
                    {"detail": "Not correct ZIP file archive."},
                    status=status.HTTP_400_BAD_REQUEST
                )

            try:
                with zipfile.ZipFile(io.BytesIO(archive_bytes)) as zf:
                    file_list = zf.namelist()

                    valid_dicoms = [
                        name for name in file_list 
                        if not name.startswith("__MACOSX") 
                        and not name.endswith(".DS_Store") 
                        and not name.endswith("/")
                    ]

                    if not valid_dicoms:
                        return Response(
                            {"detail": "No files in archive."},
                            status=status.HTTP_400_BAD_REQUEST
                        )

                    study_uids = set()
                    for name in valid_dicoms:
                        try:
                            with zf.open(name) as dicom_file:
                                ds = pydicom.dcmread(dicom_file, stop_before_pixels=True)
                                if hasattr(ds, "StudyInstanceUID"):
                                    study_uids.add(str(ds.StudyInstanceUID))
                        except Exception:
                            pass

                    if not study_uids:
                        return Response(
                            {"detail": "No valid DICOM metadata found in archive files."},
                            status=status.HTTP_400_BAD_REQUEST
                        )

                    if len(study_uids) > 1:
                        return Response(
                            {
                                "code": "multiple_studies_error",
                                "detail": "The ZIP archive contains files from multiple different studies (different StudyInstanceUID). Please upload one study per archive."
                            },
                            status=status.HTTP_400_BAD_REQUEST
                        )

                    zip_key = f"ZIP/{archive_file.name}"
                    put_bytes(archive_bytes, "studies", zip_key)

            except zipfile.BadZipFile:
                return Response(
                    {"detail": "ZIP archive is damaged."},
                    status=status.HTTP_400_BAD_REQUEST
                )

            try:
                orthanc_client = OrthancClient()
                orthanc_response = orthanc_client.upload_dicom_zip(archive_bytes)

                
                # Obsługa zależnie od tego, co wyświetli się w konsoli:
                if isinstance(orthanc_response, dict):
                    orthanc_study_id = orthanc_response.get("ParentStudy") or orthanc_response.get("ID")
                elif isinstance(orthanc_response, list) and len(orthanc_response) > 0:
                    first_item = orthanc_response[0]
                    if isinstance(first_item, dict):
                        orthanc_study_id = first_item.get("ParentStudy") or first_item.get("ID")
                    else:
                        orthanc_study_id = str(first_item)

                if not orthanc_study_id:
                    # Fallback – pobierz ostatnie badanie z listy, jeśli Orthanc nic konkretnego nie zwrócił w ID
                    studies_list = orthanc_client.list_studies()
                    if studies_list:
                        orthanc_study_id = studies_list[0].get("orthanc_id")

            except OrthancUnauthorized:
                return Response(
                    {
                        "code": "orthanc_unauthorized",
                        "detail": "Orthanc (DICOM server) rejected the backend's credentials during upload.",
                    },
                    status=status.HTTP_503_SERVICE_UNAVAILABLE,
                )
            except OrthancUnavailable:
                return Response(
                    {
                        "code": "orthanc_unavailable",
                        "detail": "Orthanc (DICOM server) is unavailable during upload.",
                    },
                    status=status.HTTP_503_SERVICE_UNAVAILABLE,
                )
            study = Study.objects.create(
                orthanc_path=orthanc_study_id
            )
            

        # 3. If a report file (.txt / scan) is attached, upload it to MinIO
        if report_file:
            file_bytes = report_file.read()
            key = f"reports/{report_file.name}"
            put_bytes(file_bytes,"reports",key,report_file.content_type)

            # Create a related entry in the ExtractionResult table[cite: 1]
            # (If there was no DICOM, the study field will be NULL, allowing unassigned reports)
            ExtractionResult.objects.create(
                study=study,
                generated_report=key,
            )
            current_app.send_task("extraction.run", kwargs={"keys": [key]})
        return Response(
            {
                "detail": "Study and documents have been successfully imported.",
                "study_id": study.id if study else None,
                "orthanc_path": orthanc_study_id
            },
            status=status.HTTP_201_CREATED
        )
    except Exception as e:
        return Response(
            {
                "code": "server_error",
                "detail": f"An unexpected error occurred during import: {str(e)}",
            },
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )

@api_view(["POST"])
@require_permission(["addStudies"])
@parser_classes([MultiPartParser, FormParser])
def attach_report_to_study(request, orthanc_id):
    """
    Endpoint attaching new file to existing study using orthanc_path
    """
    study = get_object_or_404(Study, orthanc_path=orthanc_id)
    report_file = request.FILES.get("report")

    if not report_file:
        return Response(
            {"detail": "No report file provided."},
            status=status.HTTP_400_BAD_REQUEST
        )
    try:
        file_bytes = report_file.read()
        key = f"reports/{report_file.name}"
        put_bytes(file_bytes, "reports", key, report_file.content_type)
        ExtractionResult.objects.create(
            study=study,
            generated_report=key,
        )
        current_app.send_task("extraction.run", kwargs={"keys": [key]})

        return Response(
            {"detail": "Report successfully attached to the study."},
            status=status.HTTP_200_OK
        )
    except Exception as e:
        return Response(
            {
                "code": "server_error",
                "detail": f"An unexpected error occurred: {str(e)}",
            },
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )

@api_view(["POST"])
@require_permission(["addStudies"])
def attach_existing_report(request, orthanc_id):
    """
    
    """
    study = get_object_or_404(Study, orthanc_path=orthanc_id)
    report_id = request.data.get("report_id")

    if not report_id:
        return Response(
            {"detail": "No report_id provided."},
            status=status.HTTP_400_BAD_REQUEST
        )

    try:
        extraction = get_object_or_404(ExtractionResult, id=report_id, study__isnull=True)
        extraction.study = study
        extraction.save()

        return Response(
            {"detail": "Existing report successfully attached to the study."},
            status=status.HTTP_200_OK
        )
    except Exception as e:
        return Response(
            {
                "code": "server_error",
                "detail": f"An unexpected error occurred: {str(e)}",
            },
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )

@api_view(["GET"])
@permission_classes([IsAuthenticated])
def unassigned_reports_list(request):
    try:
        unassigned = ExtractionResult.objects.filter(study__isnull=True)
        
        response_data = []
        for item in unassigned:
            file_name = item.generated_report.split("/")[-1] if item.generated_report else "unknown"
            
            # Określamy rodzaj pliku na podstawie rozszerzenia
            ext = file_name.split(".")[-1].lower()
            kind = "scan" if ext in ["jpg", "jpeg", "png"] else "text"

            response_data.append({
                "id": str(item.id),
                "fileName": file_name,
                "kind": kind,
                "addedAt": item.created_at.strftime("%Y-%m-%d") if hasattr(item, "created_at") and item.created_at else None,
            })

        return Response(response_data, status=status.HTTP_200_OK)

    except Exception as e:
        return Response(
            {
                "code": "server_error",
                "detail": f"An unexpected error occurred: {str(e)}",
            },
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )

@api_view(["GET"])
@permission_classes([IsAuthenticated])
def dashboard_view(request):
    try:
        orthanc_client = OrthancClient()
        orthanc_studies = orthanc_client.list_studies()
    except (OrthancUnauthorized, OrthancUnavailable):
        orthanc_studies = []

    queue_items = []
    processing_count = 0
    to_review_count = 0
    in_progress_items = []

    for idx, o_study in enumerate(orthanc_studies):
        orthanc_id = o_study.get("orthanc_id")
        
        db_study = Study.objects.filter(orthanc_path=orthanc_id).first()
        
        extraction = None
        segmentation = None
        if db_study:
            extraction = ExtractionResult.objects.filter(study=db_study).first()
            segmentation = SegmentationResult.objects.filter(study=db_study).first()

        seg_status = segmentation.status if segmentation else "PENDING"
        ext_status = extraction.status if extraction else "PENDING"
        
        uncertainty = None
        if segmentation and segmentation.uncertainty is not None:
            uncertainty = segmentation.uncertainty
        elif extraction and extraction.uncertainty is not None:
            uncertainty = extraction.uncertainty
        else:
            uncertainty = 0.5

        study_number = str(idx + 1).zfill(4)

        if seg_status in ["PROCESSING", "PENDING"] or ext_status in ["PROCESSING", "PENDING"]:
            processing_count += 1
            if len(in_progress_items) < 5:
                stage = "segmentation" if seg_status == "PROCESSING" else "extraction"
                state = "running" if (seg_status == "PROCESSING" or ext_status == "PROCESSING") else "queued"
                in_progress_items.append({
                    "studyNumber": study_number,
                    "stage": stage,
                    "state": state
                })
        else:
            to_review_count += 1

        queue_items.append({
            "studyId": str(db_study.id) if db_study else f"s{idx + 1}",
            "studyNumber": study_number,
            "patientId": o_study.get("patient_id") or f"P-{str(101 + idx).zfill(4)}",
            "studyDate": o_study.get("study_date") or "2026-10-26",
            "uncertainty": float(uncertainty),
        })

    missing_reports_count = ExtractionResult.objects.filter(study__isnull=True).count()
    
    attention_items = []
    if missing_reports_count > 0:
        attention_items.append({
            "kind": "missing_report",
            "subject": "",
            "count": missing_reports_count,
            "href": "/badania"
        })

    dashboard_data = {
        "toReview": to_review_count or len(queue_items),
        "processing": processing_count,
        "verifiedToday": 6,
        "queue": queue_items,
        "attention": attention_items,
        "inProgress": in_progress_items,
        "verifiedLastWeek": [
            { "date": "2026-10-20", "unchanged": 5, "corrected": 2 },
            { "date": "2026-10-21", "unchanged": 7, "corrected": 3 },
            { "date": "2026-10-22", "unchanged": 6, "corrected": 2 },
            { "date": "2026-10-23", "unchanged": 8, "corrected": 3 },
            { "date": "2026-10-24", "unchanged": 6, "corrected": 3 },
            { "date": "2026-10-25", "unchanged": 4, "corrected": 2 },
            { "date": "2026-10-26", "unchanged": 4, "corrected": 2 },
        ],
    }

    return Response(dashboard_data, status=status.HTTP_200_OK)