"""Errors of talking to Orthanc, the DICOM server."""

from common.errors import AppError


class OrthancUnavailable(AppError):
    """Orthanc could not be reached or returned an unusable response."""

    code = "orthanc_unavailable"
    status_code = 503
    detail = "Orthanc (DICOM server) is unavailable."


class OrthancUnauthorized(OrthancUnavailable):
    """Orthanc is reachable but rejected the request (HTTP 401)."""

    code = "orthanc_unauthorized"
    detail = "Orthanc (DICOM server) rejected the backend's credentials."


class StudyNotFound(AppError):
    """Orthanc has no study with the given StudyInstanceUID."""

    code = "study_not_found"
    status_code = 404
    detail = "Orthanc (DICOM server) nie ma takiego badania."
