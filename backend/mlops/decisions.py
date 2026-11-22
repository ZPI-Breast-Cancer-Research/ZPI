"""What the decisions on a version (propose, promote, reject, ...) of any module share."""

from rest_framework import status
from rest_framework.response import Response

from .models import ModelVersion

# a version that waits for a decision: a draft or a proposal
UNDECIDED = (ModelVersion.StatusChoices.NEW, ModelVersion.StatusChoices.CANDIDATE)


def wrong_status(model: ModelVersion, allowed) -> Response | None:
    """409 when the version is not in a status the action applies to, otherwise None."""
    if model.status in allowed:
        return None
    return Response(
        {
            "code": "wrong_status",
            "detail": f"Wersja {model.version} ma status „{model.get_status_display()}”, "
            "tej operacji nie można na niej wykonać.",
        },
        status=status.HTTP_409_CONFLICT,
    )
