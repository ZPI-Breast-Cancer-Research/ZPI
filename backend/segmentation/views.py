import logging

from django.shortcuts import get_object_or_404
from patients.models import Study
from rest_framework import status
from rest_framework.decorators import api_view
from rest_framework.response import Response
from segmentation.models import SegmentationResult
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
