"""Errors shared by the backend apps and the workers.

Every app keeps its own errors in ``<app>/errors.py``; they build on ``AppError`` so the API can
report them the same way (``common/exception_handler.py``).
"""

SERVER_ERROR = {
    "code": "server_error",
    "detail": "Wystąpił nieoczekiwany błąd serwera.",
}


class AppError(Exception):
    """An expected failure the API reports to the client as ``{"code", "detail"}``.

    ``code`` is stable and meant for the frontend, ``detail`` is the text the user reads, and the
    exception message (``str(error)``) is the technical reason that goes to the log.
    """

    code = SERVER_ERROR["code"]
    status_code = 500
    detail = SERVER_ERROR["detail"]

    def payload(self) -> dict[str, str]:
        return {"code": self.code, "detail": self.detail}


class StorageError(AppError):
    """Object storage (MinIO / S3) cannot be reached, is not configured or refused the request."""

    code = "storage_unavailable"
    status_code = 502
    detail = "Magazyn plików jest niedostępny; spróbuj ponownie."


class ObjectNotFound(StorageError):
    """The bucket has no object under the requested key."""

    code = "file_not_found"
    status_code = 404
    detail = "Pliku nie ma w magazynie."
