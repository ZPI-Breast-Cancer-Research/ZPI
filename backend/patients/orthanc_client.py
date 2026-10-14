"""Minimal HTTP client for Orthanc (reached via ORTHANC_URL).

Orthanc may be down or not deployed at all – every call uses short timeouts and
any network/HTTP/JSON failure is raised as ``OrthancUnavailable`` (or its subclass
``OrthancUnauthorized`` when Orthanc rejects the credentials).
"""
from urllib.parse import quote

import requests
from django.conf import settings

# (connect, read) timeouts in seconds
TIMEOUT = (2, 5)


class OrthancUnavailable(Exception):
    """Orthanc could not be reached or returned an unusable response."""


class OrthancUnauthorized(OrthancUnavailable):
    """Orthanc is reachable but rejected the request (HTTP 401)."""


class OrthancClient:
    def __init__(
        self,
        base_url: str | None = None,
        public_url: str | None = None,
        user: str | None = None,
        password: str | None = None,
    ):
        self.base_url = (base_url or settings.ORTHANC_URL).rstrip("/")
        self.public_url = (public_url or settings.ORTHANC_PUBLIC_URL).rstrip("/")
        user = settings.ORTHANC_USER if user is None else user
        password = settings.ORTHANC_PASSWORD if password is None else password
        # Basic auth only when both credentials are set.
        self.auth = (user, password) if user and password else None

    def _get(self, path: str, params: dict | None = None):
        try:
            response = requests.get(
                f"{self.base_url}{path}", params=params, auth=self.auth, timeout=TIMEOUT
            )
        except requests.RequestException as exc:
            raise OrthancUnavailable(f"Orthanc request {path} failed: {exc}") from exc
        if response.status_code == 401:
            raise OrthancUnauthorized(f"Orthanc rejected credentials for {path} (HTTP 401)")
        try:
            response.raise_for_status()
            return response.json()
        except (requests.RequestException, ValueError) as exc:
            raise OrthancUnavailable(f"Orthanc request {path} failed: {exc}") from exc

    def status(self) -> str:
        """``ok``, ``unauthorized`` or ``unreachable`` based on ``GET /system``."""
        try:
            self._get("/system")
        except OrthancUnauthorized:
            return "unauthorized"
        except OrthancUnavailable:
            return "unreachable"
        return "ok"

    def list_studies(self) -> list[dict]:
        raw = self._get("/studies", params={"expand": "", "requestedTags": "ModalitiesInStudy"})
        if not isinstance(raw, list):
            raise OrthancUnavailable("Orthanc /studies returned an unexpected payload")
        return [self.map_study(study) for study in raw]

    def viewer_url(self, study_instance_uid: str | None) -> str | None:
        if not study_instance_uid:
            return None
        return f"{self.public_url}/ohif/viewer?StudyInstanceUIDs={quote(study_instance_uid)}"

    def map_study(self, study: dict) -> dict:
        tags = study.get("MainDicomTags", {})
        patient_tags = study.get("PatientMainDicomTags", {})
        requested = study.get("RequestedTags", {})
        modalities = requested.get("ModalitiesInStudy") or tags.get("ModalitiesInStudy") or ""
        uid = tags.get("StudyInstanceUID")
        return {
            "orthanc_id": study.get("ID"),
            "study_instance_uid": uid,
            "patient_id": patient_tags.get("PatientID"),
            "study_date": tags.get("StudyDate"),
            "description": tags.get("StudyDescription"),
            "modalities": [m for m in modalities.split("\\") if m],
            "series_count": len(study.get("Series", [])),
            "viewer_url": self.viewer_url(uid),
        }
