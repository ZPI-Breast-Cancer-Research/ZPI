import logging

from celery import current_app
from django.db import transaction
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import status
from rest_framework.decorators import api_view, parser_classes
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.response import Response

from common.storage import BUCKET_MASKS, put_bytes
from patients.models import Study
from segmentation.models import SegmentationResult, StatusChoices
from users.permissions import require_permission

logger = logging.getLogger(__name__)


def _latest(study: Study) -> SegmentationResult | None:
    return SegmentationResult.objects.filter(study=study).order_by("-id").first()


@api_view(["GET"])
@require_permission(["review", "viewModels"])
def get_segmentation_result(request, study_id: int):
    """Status and metadata of the newest segmentation result of a study."""
    study = get_object_or_404(Study, pk=study_id)
    result = _latest(study)

    if not result:
        return Response(
            {"detail": "Brak wyniku segmentacji dla podanego badania"},
            status=status.HTTP_404_NOT_FOUND,
        )

    return Response(
        {
            "id": result.id,
            "study_id": study.id,
            "status": result.status,
            "uncertainty": result.uncertainty,
            "model_version": result.model.version if result.model else None,
            "generated_path": result.generated_path,
            "accepted_path": result.accepted_path,
            "accepted_at": result.accepted_at,
        },
        status=status.HTTP_200_OK,
    )


@api_view(["POST"])
@parser_classes([MultiPartParser, FormParser])
@require_permission("review")
def approve_segmentation(request, study_id: int):
    """
    Zatwierdza maskę modelu albo zapisuje poprawioną maskę (pole ``mask_file``, NIfTI).
    Poprawiona maska trafia do MinIO, a po commicie transakcji task CPU
    segmentation.correction_to_dicom_seg zapisuje zatwierdzoną maskę w Orthancu jako DICOM SEG.
    """
    study = get_object_or_404(Study, pk=study_id)
    corrected_file = request.FILES.get("mask_file")

    try:
        with transaction.atomic():
            result = (
                SegmentationResult.objects.select_for_update()
                .filter(study=study)
                .order_by("-id")
                .first()
            )
            if not result:
                return Response(
                    {"detail": "Nie znaleziono rekordu segmentacji do zatwierdzenia."},
                    status=status.HTTP_404_NOT_FOUND,
                )
            if result.status != StatusChoices.COMPLETED:
                return Response(
                    {"detail": f"Nie można zatwierdzić wyniku w statusie {result.status}."},
                    status=status.HTTP_409_CONFLICT,
                )

            if corrected_file:
                # Radiolog poprawił maskę -> osobny plik, maska modelu zostaje bez zmian
                accepted_key = f"{study.id}/{result.id}_corrected.nii.gz"
                put_bytes(corrected_file.read(), BUCKET_MASKS, accepted_key, "application/gzip")
                result.status = StatusChoices.CORRECTED
            else:
                accepted_key = result.generated_path
                result.status = StatusChoices.APPROVED

            result.accepted_path = accepted_key
            result.accepted_by = request.user
            result.accepted_at = timezone.now().date()
            result.save(update_fields=["status", "accepted_path", "accepted_by", "accepted_at"])

            if study.orthanc_path:
                orthanc_study_id = study.orthanc_path
                result_id = result.id
                transaction.on_commit(
                    lambda: current_app.send_task(
                        "segmentation.correction_to_dicom_seg",
                        kwargs={
                            "orthanc_study_id": orthanc_study_id,
                            "mask_key": accepted_key,
                            "result_id": result_id,
                        },
                    )
                )
    except Exception:
        logger.exception("Błąd podczas zatwierdzania segmentacji dla badania %s", study_id)
        return Response(
            {"code": "server_error", "detail": "Wystąpił błąd podczas zatwierdzania maski."},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )

    logger.info("Zatwierdzono segmentację dla badania %s (rekord ID: %s)", study.id, result.id)
    return Response(
        {
            "detail": "Maska została pomyślnie zatwierdzona.",
            "status": result.status,
            "accepted_path": result.accepted_path,
        },
        status=status.HTTP_200_OK,
    )
