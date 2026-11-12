from django.db import DatabaseError, connection
from rest_framework import status
from rest_framework.decorators import api_view
from rest_framework.response import Response
from django.conf import settings
from django.utils import timezone

from mlops.mlflow_client import MlflowClient
from patients.orthanc_client import OrthancClient
from common.storage import is_avaible
from users.permissions import require_permission

def _database_ok() -> bool:
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
    except DatabaseError:
        return False
    return True


# Orthanc client status -> state of the "orthanc" component on the status page
ORTHANC_STATES = {"ok": "ok", "unauthorized": "unknown", "unreachable": "down"}


def _component(key, state, detail=None) -> dict:
    return {"key": key, "state": state, "since": None, "detail": detail}


@api_view(["GET"])
def health(request):
    """200 while the API and DB are up (the rest is reported only); 503 if the DB is down.

    The top-level keys are what the PACS indicator and the container healthcheck read;
    "components" feeds the status page. A component nothing checks yet is "unknown", not "ok".
    """
    db_ok = _database_ok()
    orthanc = OrthancClient().status()
    mlflow = MlflowClient().status()
    # the workers need the database; while it is up nothing here checks them yet
    worker_state = "unknown" if db_ok else "down"

    body = {
        "status": "ok" if db_ok else "error",
        "database": "ok" if db_ok else "error",
        "orthanc": orthanc,
        "mlflow": mlflow,
        "storage": "ok" if is_avaible() else "error",
        "checkedAt": timezone.now().isoformat(),
        "components": [
            _component(
                "orthanc",
                ORTHANC_STATES.get(orthanc, "unknown"),
                "401" if orthanc == "unauthorized" else None,
            ),
            _component("pacs", "unknown"),
            _component("segmentation", worker_state),
            _component("extraction", worker_state),
            _component("training", worker_state),
            _component("llm", "unknown"),
            _component("registry", "ok" if mlflow == "ok" else "down", "MLflow"),
        ],
        "profile": getattr(settings, "SYSTEM_PROFILE", "gpu1"),
        "retraining": getattr(settings, "RETRAIN_ENABLED", True),
    }
    return Response(body, status=status.HTTP_200_OK if db_ok else status.HTTP_503_SERVICE_UNAVAILABLE)


@api_view(["GET"])
@require_permission(["review"])
def orthanc_auth(request):
    return Response(status=status.HTTP_204_NO_CONTENT)
