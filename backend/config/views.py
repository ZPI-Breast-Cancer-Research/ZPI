from datetime import datetime
from django.db import DatabaseError, connection
from rest_framework import status
from rest_framework.decorators import api_view
from rest_framework.response import Response
from django.conf import settings
from django.utils import timezone

from mlops.mlflow_client import MlflowClient
from patients.orthanc_client import OrthancClient, OrthancUnauthorized, OrthancUnavailable
from common.storage import is_avaible
from users.permissions import require_permission

def _database_ok() -> bool:
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
    except DatabaseError:
        return False
    return True


@api_view(["GET"])
def health(request):
    db_ok = _database_ok()
    
    orthanc_status = "ok"
    orthanc_detail = None
    try:
        o_status = OrthancClient().status()
        if o_status != "ok":
            orthanc_status = "down"
    except OrthancUnauthorized:
        orthanc_status = "unknown"
        orthanc_detail = "401"
    except OrthancUnavailable:
        orthanc_status = "down"

    try:
        mlflow_ok = MlflowClient().status() == "ok"
    except Exception:
        mlflow_ok = False

    components = [
        {
            "key": "orthanc",
            "state": orthanc_status,
            "since": None,
            "detail": orthanc_detail,
        },
        {
            "key": "pacs",
            "state": "ok" if orthanc_status == "ok" else "down",
            "since": None,
            "detail": "AE MARIA → PACS_SZPITAL",
        },
        {
            "key": "segmentation",
            "state": "ok" if db_ok else "down",
            "since": None,
            "detail": "Kolejka aktywna",
        },
        {
            "key": "extraction",
            "state": "ok" if db_ok else "down",
            "since": None,
            "detail": None,
        },
        {
            "key": "training",
            "state": "ok",
            "since": None,
            "detail": None,
        },
        {
            "key": "llm",
            "state": "ok",
            "since": None,
            "detail": None,
        },
        {
            "key": "registry",
            "state": "ok" if mlflow_ok else "down",
            "since": None,
            "detail": "MLflow",
        },
    ]

    body = {
        "checkedAt": timezone.now().isoformat(),
        "components": components,
        "profile": getattr(settings, "SYSTEM_PROFILE", "gpu1"),
        "retraining": getattr(settings, "RETRAIN_ENABLED", True),
    }

    http_status = status.HTTP_200_OK if db_ok else status.HTTP_503_SERVICE_UNAVAILABLE
    return Response(body, status=http_status)

@api_view(["GET"])
@require_permission(["review"])
def orthanc_auth(request):
    return Response(status=status.HTTP_204_NO_CONTENT)
