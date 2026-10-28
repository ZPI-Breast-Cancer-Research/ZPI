from rest_framework import status
from rest_framework.decorators import api_view, parser_classes
from rest_framework.parsers import MultiPartParser, FormParser
from rest_framework.response import Response

from .orthanc_client import OrthancClient, OrthancUnauthorized, OrthancUnavailable
from .models import Study, ExtractionResult  # Models matching the ERD schema[cite: 1]
from common.storage import upload_to_minio


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
    dicom_files = request.FILES.getlist("dicoms")
    report_file = request.FILES.get("report")

    # Validation: did the user provide any files?
    if not dicom_files and not report_file:
        return Response(
            {"detail": "No files were provided for import."},
            status=status.HTTP_400_BAD_REQUEST
        )

    study = None
    orthanc_study_id = None

    try:
        # 2. If DICOM files are present, send them to Orthanc
        if dicom_files:
            orthanc_client = OrthancClient()
            
            # Note: depending on your orthanc_client implementation, 
            # call the method that uploads files and returns the study ID from Orthanc.
            # Example: orthanc_response = orthanc_client.upload_files(dicom_files)
            # orthanc_study_id = orthanc_response.get("ID")
            
            orthanc_study_id = "mock_orthanc_uid_12345"  # Replace with actual client response

            # Create an entry in the Study table (saving the Orthanc identifier)[cite: 1]
            study = Study.objects.create(
                orthanc_path=orthanc_study_id
            )

        # 3. If a report file (.txt / scan) is attached, upload it to MinIO
        if report_file:
            minio_file_path = upload_to_minio(report_file)

            # Create a related entry in the ExtractionResult table[cite: 1]
            # (If there was no DICOM, the study field will be NULL, allowing unassigned reports)
            ExtractionResult.objects.create(
                study=study,
                generated_report={"file_path": minio_file_path},
                status="pending"  # Initial status waiting for worker extraction
            )

        return Response(
            {
                "detail": "Study and documents have been successfully imported.",
                "study_id": study.id if study else None,
                "orthanc_path": orthanc_study_id
            },
            status=status.HTTP_201_CREATED
        )

    except (OrthancUnauthorized, OrthancUnavailable):
        return Response(
            {
                "code": "orthanc_error",
                "detail": "Failed to connect to the DICOM server (Orthanc). Check configuration.",
            },
            status=status.HTTP_503_SERVICE_UNAVAILABLE,
        )
    except Exception as e:
        return Response(
            {
                "code": "server_error",
                "detail": f"An unexpected error occurred during import: {str(e)}",
            },
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )