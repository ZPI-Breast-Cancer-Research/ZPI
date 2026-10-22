from django.db import DatabaseError, connection
from rest_framework import status
from rest_framework.decorators import api_view
from rest_framework.response import Response

from mlops.mlflow_client import MlflowClient
from patients.orthanc_client import OrthancClient


def _database_ok() -> bool:
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
    except DatabaseError:
        return False
    return True


@api_view(["GET"])
def health(request):
    """200 while the API and DB are up (Orthanc, MLflow: reported only); 503 if the DB is down."""
    db_ok = _database_ok()
    body = {
        "status": "ok" if db_ok else "error",
        "database": "ok" if db_ok else "error",
        "orthanc": OrthancClient().status(),
        "mlflow": MlflowClient().status(),
    }
    return Response(body, status=status.HTTP_200_OK if db_ok else status.HTTP_503_SERVICE_UNAVAILABLE)


@api_view(["GET"])
def orthanc_auth(request):
    return Response(status=status.HTTP_204_NO_CONTENT)
