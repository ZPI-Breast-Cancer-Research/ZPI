"""Minimal HTTP client for Orthanc (reached via ORTHANC_URL).

Orthanc may be down or not deployed at all – every call uses short timeouts and
any network/HTTP/JSON failure is raised as ``OrthancUnavailable`` (or its subclass
``OrthancUnauthorized`` when Orthanc rejects the credentials).
"""
import io
import zipfile
from pathlib import Path
from urllib.parse import quote

import requests
from django.conf import settings

# (connect, read) timeouts in seconds
TIMEOUT = (2, 5)
DOWNLOAD_TIMEOUT = (2, 60)

SERIES_INSTANCE_UID = "0020000E"


class OrthancUnavailable(Exception):
    """Orthanc could not be reached or returned an unusable response."""


class OrthancUnauthorized(OrthancUnavailable):
    """Orthanc is reachable but rejected the request (HTTP 401)."""


class StudyNotFound(Exception):
    """Orthanc has no study with the given StudyInstanceUID."""


def _tag(item: dict, tag: str) -> str:
    """First value of a tag in a DICOM JSON item, e.g. ``_tag(series, "0020000E")``."""
    try:
        return item[tag]["Value"][0]
    except (KeyError, IndexError, TypeError) as exc:
        raise OrthancUnavailable(f"Orthanc response has no value for tag {tag}") from exc


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

    def _request(
        self, path: str, params: dict | None = None, timeout=TIMEOUT
    ) -> requests.Response:
        """GET from Orthanc; failures raise OrthancUnavailable or OrthancUnauthorized."""
        try:
            response = requests.get(
                f"{self.base_url}{path}", params=params, auth=self.auth, timeout=timeout
            )
        except requests.RequestException as exc:
            raise OrthancUnavailable(f"Orthanc request {path} failed: {exc}") from exc
        if response.status_code == 401:
            raise OrthancUnauthorized(f"Orthanc rejected credentials for {path} (HTTP 401)")
        try:
            response.raise_for_status()
        except requests.RequestException as exc:
            raise OrthancUnavailable(f"Orthanc request {path} failed: {exc}") from exc
        return response

    def _get(self, path: str, params: dict | None = None):
        """GET and parse the JSON body."""
        response = self._request(path, params)
        try:
            return response.json()
        except ValueError as exc:
            raise OrthancUnavailable(f"Orthanc {path} returned invalid JSON: {exc}") from exc

    def download_all_instances(self, study_uid: str, dest: Path) -> None:
        """Download all instances of a study using DICOMweb (QIDO-RS and WADO-RS)."""
        series_list = self.list_series(study_uid)
        if not series_list:
            raise StudyNotFound(f"Orthanc has no study {study_uid}")

        dest.mkdir(parents=True, exist_ok=True)
        for series_uid in series_list:
            response = self._request(f"/dicom-web/studies/{study_uid}/series/{series_uid}/instances")
            instances = response.json()
            for instance in instances:
                sop_instance_uid = _tag(instance, "00080018")
                instance_response = self._request(
                    f"/dicom-web/studies/{study_uid}/series/{series_uid}/instances/{sop_instance_uid}"
                )
                with open(dest / f"{sop_instance_uid}.dcm", "wb") as f:
                    f.write(instance_response.content)
        """SeriesInstanceUIDs of a study (QIDO-RS)."""
        series = self._get(f"/dicom-web/studies/{study_uid}/series")
        # Orthanc answers an unknown study with 200 and an empty list, not 404.
        if not series:
            raise StudyNotFound(f"Orthanc has no study {study_uid}")
        return [_tag(item, SERIES_INSTANCE_UID) for item in series]

    def download_study(self, orthanc_id: str, dest: Path) -> Path:
        """Download one study and unpack its DICOM files into ``dest``.

        ``orthanc_id`` is Orthanc's own study id (``Study.orthanc_path``), not a
        StudyInstanceUID. Orthanc returns the study as a zip archive.
        """
        response = self._request(
            f"/studies/{quote(orthanc_id, safe='')}/archive",
            timeout=DOWNLOAD_TIMEOUT,
        )
        payload = io.BytesIO(response.content)
        if not zipfile.is_zipfile(payload):
            raise OrthancUnavailable(
                f"Orthanc /studies/{orthanc_id}/archive did not return a zip archive"
            )
        payload.seek(0)
        dest.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(payload) as archive:
            for member in archive.namelist():
                target = (dest / member).resolve()
                if not target.is_relative_to(dest.resolve()):
                    raise OrthancUnavailable(f"Orthanc archive has an unsafe path: {member}")
            archive.extractall(dest)
        return dest

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

    def upload_dicom_zip(self, zip_bytes: bytes) -> dict:
        url = f"{self.base_url}/instances"
        headers = {"Content-Type": "application/zip"}
        
        try:
            response = requests.post(
                url, 
                data=zip_bytes, 
                auth=self.auth, 
                headers=headers, 
                timeout=TIMEOUT
            )
        except requests.RequestException as exc:
            raise OrthancUnavailable(f"Orthanc upload to {url} failed: {exc}") from exc

        if response.status_code == 401:
            raise OrthancUnauthorized(f"Orthanc rejected credentials during upload (HTTP 401)")
            
        try:
            response.raise_for_status()
            return response.json()
        except (requests.RequestException, ValueError) as exc:
            raise OrthancUnavailable(f"Orthanc upload response invalid: {exc}") from exc

    
