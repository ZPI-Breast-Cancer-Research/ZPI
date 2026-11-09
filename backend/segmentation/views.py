from rest_framework import status
from rest_framework.decorators import api_view, parser_classes
from rest_framework.parsers import MultiPartParser, FormParser
from rest_framework.response import Response
from django.shortcuts import get_object_or_404
from django.db import transaction
from celery import current_app

from common.storage import BUCKET_MASKS, upload_file
from patients.models import Study
from segmentation.models import SegmentationResult, StatusChoices


@api_view["POST"]
@parser_classes([MultiPartParser, FormParser])
def get_segmentation_result(result, study_id: int):
    """
    Pobiera metadane i status najnowszego wyniku segmentacji dla danego badania
    """

    study = get_object_or_404(Study, pk=study_id)
    result = SegmentationResult.objecs.filter(study=study).last()
    
    if not result:
        return Response(
                {"detail": "Brak wyniku segmentacji dla podanego badania"}, 
                status=status.HTTP_404_NOT_FOUND)

    return Response(
            {
                "id": result.id,
                "study_id": study.id,
                "status": result.status,
                "uncertainity": result.uncertainity,
                "model_version": result.model_version,
                "generated_path": result.generated_path,
                "corrected_path": result.corrected_path,
                "volume_ml": getattr(result, "volume_ml", None),
                "lesion_dimensions_mm": getattr(result, "lesion_dimensions_mm", None),
                "created_at": result.created_at if hasattr(result, "created_at") else None
                },
            status=status.HTTP_200_OK,
            )

@api_view(["POST"])
@parser_classes([MultiPartParser, FormParser])
def approve_segmentation(request, study_id: int):
    """
    Zatwierdza lub nadpisuje maskę segmentacji dla badania.
    Zapisuje plik NIfTI w MinIO, zmienia status w bazie i wysyła task CPU
    segmentation.correction_to_dicom_seg do Celery po commit transakcji.
    """
    study = get_object_or_404(Study, pk=study_id)
    result = SegmentationResult.objects.filter(study=study).last()

    if not result:
        return Response(
            {"detail": "Nie znaleziono rekordu segmentacji do zatwierdzenia."},
            status=status.HTTP_404_NOT_FOUND,
        )

    corrected_file = request.FILES.get("mask_file")
    
    try:
        with transaction.atomic():
            corrected_key = result.generated_path

            if corrected_file:
                # Radiolog nanosił poprawki pędzlem -> tworzymy nową ścieżkę w MinIO
                corrected_key = f"{study.id}/corrected_mask.nii.gz"
                upload_file(corrected_file, BUCKET_MASKS, corrected_key)
                result.corrected_path = corrected_key
            else:
                # Radiolog zatwierdził maskę wygenerowaną przez model bez zmian
                result.corrected_path = result.generated_path

            result.status = StatusChoices.VERIFIED
            result.save(update_fields=["status", "corrected_path"])

            # 2. Bezpieczne zlecenie taska CPU (konwersja do DICOM SEG i wysyłka do Orthanc)
            # Wzorzec transaction.on_commit chroni przed race-condition (Driver Q3)
            if study.orthanc_path:
                transaction.on_commit(
                    lambda: current_app.send_task(
                        "segmentation.correction_to_dicom_seg",
                        kwargs={
                            "study_instance_uid": study.orthanc_path,
                            "mask_key": corrected_key,
                        },
                    )
                )

        logger.info("Zatwierdzono segmentację dla badania %s (rekord ID: %s)", study.id, result.id)
        return Response(
            {
                "detail": "Maska została pomyślnie zatwierdzona.",
                "status": result.status,
                "corrected_path": result.corrected_path,
            },
            status=status.HTTP_200_OK,
        )

    except Exception as exc:
        logger.exception("Błąd podczas zatwierdzania segmentacji dla badania %s", study_id)
        return Response(
            {"code": "server_error", "detail": f"Wystąpił błąd: {str(exc)}"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )
