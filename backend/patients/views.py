from rest_framework import status
from rest_framework.decorators import api_view, parser_classes
from rest_framework.parsers import MultiPartParser, FormParser
from rest_framework.response import Response

from .orthanc_client import OrthancClient, OrthancUnauthorized, OrthancUnavailable
from .models import Study 
from common.storage import put_bytes
from extraction.models import ExtractionResult
import zipfile
import io


@api_view(["GET"])
def study_list(request):
    try:
        studies = OrthancClient().list_studies()
    except OrthancUnauthorized:
        return Response(
            {
                "code": "orthanc_unauthorized",
                "detail": "Orthanc (DICOM server) rejected the backend's credentials. "
                "Check ORTHANC_USER and ORTHANC_PASSWORD.",
            },
            status=status.HTTP_503_SERVICE_UNAVAILABLE,
        )
    except OrthancUnavailable:
        return Response(
            {
                "code": "orthanc_unavailable",
                "detail": "Orthanc (DICOM server) is unavailable. Check that it is running "
                "and that ORTHANC_URL is configured correctly.",
            },
            status=status.HTTP_503_SERVICE_UNAVAILABLE,
        )
    return Response(studies)


@api_view(["POST"])
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

                    zip_key = f"ZIP/{archive_file.name}"
                    put_bytes(archive_bytes, "studies", zip_key)

            except zipfile.BadZipFile:
                return Response(
                    {"detail": "ZIP archive is damaged."},
                    status=status.HTTP_400_BAD_REQUEST
                )
            study = Study.objects.create(
                orthanc_path=None
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
                generated_report={"file_path": key},
            )

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