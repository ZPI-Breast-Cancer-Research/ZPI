from rest_framework import status
from rest_framework.decorators import api_view
from rest_framework.response import Response

from .orthanc_client import OrthancClient, OrthancUnauthorized, OrthancUnavailable


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
