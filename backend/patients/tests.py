import io
import zipfile
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock

import requests
from django.test import SimpleTestCase, override_settings
from rest_framework.test import APIClient

from .orthanc_client import DOWNLOAD_TIMEOUT, OrthancClient, OrthancUnavailable

ORTHANC_STUDY = {
    "ID": "27f7126f-4f66c3e1-f1e5c8f8-5b8e4f32-9a6bce10",
    "MainDicomTags": {
        "StudyInstanceUID": "1.2.840.113619.2.55.3.1234",
        "StudyDate": "20240115",
        "StudyDescription": "MRI BREAST BILATERAL",
    },
    "PatientMainDicomTags": {"PatientID": "PAT-001"},
    "RequestedTags": {"ModalitiesInStudy": "MR\\SR"},
    "Series": ["s1", "s2", "s3"],
}


def _response(payload, status_code=200):
    response = mock.Mock(status_code=status_code)
    response.json.return_value = payload
    if status_code >= 400:
        response.raise_for_status.side_effect = requests.HTTPError(f"{status_code} error")
    return response


@override_settings(
    ORTHANC_URL="http://orthanc.test:8042",
    ORTHANC_PUBLIC_URL="http://public.test",
    ORTHANC_USER="",
    ORTHANC_PASSWORD="",
)
class StudyListTests(SimpleTestCase):
    url = "/api/studies"

    def setUp(self):
        self.client = APIClient()

    @mock.patch("patients.orthanc_client.requests.get")
    def test_lists_studies(self, get):
        get.return_value = _response([ORTHANC_STUDY])

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json(),
            [
                {
                    "orthanc_id": ORTHANC_STUDY["ID"],
                    "study_instance_uid": "1.2.840.113619.2.55.3.1234",
                    "patient_id": "PAT-001",
                    "study_date": "20240115",
                    "description": "MRI BREAST BILATERAL",
                    "modalities": ["MR", "SR"],
                    "series_count": 3,
                    "viewer_url": "http://public.test/ohif/viewer"
                    "?StudyInstanceUIDs=1.2.840.113619.2.55.3.1234",
                }
            ],
        )
        self.assertEqual(get.call_args.args[0], "http://orthanc.test:8042/studies")
        self.assertIsNotNone(get.call_args.kwargs["timeout"])

    @mock.patch("patients.orthanc_client.requests.get")
    def test_empty_list(self, get):
        get.return_value = _response([])

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), [])

    @mock.patch("patients.orthanc_client.requests.get")
    def test_orthanc_unreachable(self, get):
        get.side_effect = requests.ConnectionError("connection refused")

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json()["code"], "orthanc_unavailable")
        self.assertIn("Orthanc", response.json()["detail"])

    @mock.patch("patients.orthanc_client.requests.get")
    def test_orthanc_server_error(self, get):
        get.return_value = _response({"error": "boom"}, status_code=500)

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json()["code"], "orthanc_unavailable")

    @mock.patch("patients.orthanc_client.requests.get")
    def test_orthanc_unauthorized(self, get):
        get.return_value = _response({}, status_code=401)

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json()["code"], "orthanc_unauthorized")
        self.assertIn("ORTHANC_USER", response.json()["detail"])

    @mock.patch("patients.orthanc_client.requests.get")
    def test_missing_tags_do_not_crash(self, get):
        get.return_value = _response([{"ID": "abc"}])

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        study = response.json()[0]
        self.assertEqual(study["modalities"], [])
        self.assertEqual(study["series_count"], 0)
        self.assertIsNone(study["viewer_url"])


class OrthancClientAuthTests(SimpleTestCase):
    @override_settings(ORTHANC_USER="orthanc", ORTHANC_PASSWORD="secret")
    @mock.patch("patients.orthanc_client.requests.get")
    def test_basic_auth_sent_when_both_set(self, get):
        get.return_value = _response({})

        OrthancClient().status()

        self.assertEqual(get.call_args.kwargs["auth"], ("orthanc", "secret"))

    @override_settings(ORTHANC_USER="orthanc", ORTHANC_PASSWORD="")
    @mock.patch("patients.orthanc_client.requests.get")
    def test_no_auth_when_password_missing(self, get):
        get.return_value = _response({})

        OrthancClient().status()

        self.assertIsNone(get.call_args.kwargs["auth"])

    @override_settings(ORTHANC_USER="", ORTHANC_PASSWORD="")
    @mock.patch("patients.orthanc_client.requests.get")
    def test_no_auth_when_unset(self, get):
        get.return_value = _response({})

        OrthancClient().status()

        self.assertIsNone(get.call_args.kwargs["auth"])


def _zip(files: dict[str, bytes]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        for name, data in files.items():
            archive.writestr(name, data)
    return buffer.getvalue()


@override_settings(
    ORTHANC_URL="http://orthanc.test:8042",
    ORTHANC_PUBLIC_URL="http://public.test",
    ORTHANC_USER="",
    ORTHANC_PASSWORD="",
)
class OrthancClientSegmentationTests(SimpleTestCase):
    @mock.patch("patients.orthanc_client.requests.get")
    def test_list_series_returns_series_uids(self, get):
        get.return_value = _response(
            [{"0020000E": {"Value": ["1.2.3"]}}, {"0020000E": {"Value": ["1.2.4"]}}]
        )

        series = OrthancClient().list_series("9.9")

        self.assertEqual(series, ["1.2.3", "1.2.4"])
        self.assertTrue(get.call_args.args[0].endswith("/dicom-web/studies/9.9/series"))

    @mock.patch("patients.orthanc_client.requests.get")
    def test_list_series_of_unknown_study_raises(self, get):
        from .orthanc_client import StudyNotFound

        get.return_value = _response([])

        with self.assertRaises(StudyNotFound):
            OrthancClient().list_series("9.9")

    @mock.patch("patients.orthanc_client.requests.get")
    def test_download_study_unpacks_archive(self, get):
        get.return_value = mock.Mock(status_code=200, content=_zip({"a/b/1.dcm": b"DICM"}))

        with TemporaryDirectory() as tmp:
            dest = OrthancClient().download_study("abc", Path(tmp) / "dicom")

            self.assertEqual((dest / "a/b/1.dcm").read_bytes(), b"DICM")
        self.assertTrue(get.call_args.args[0].endswith("/studies/abc/archive"))
        self.assertEqual(get.call_args.kwargs["timeout"], DOWNLOAD_TIMEOUT)

    @mock.patch("patients.orthanc_client.requests.get")
    def test_download_study_rejects_non_zip(self, get):
        get.return_value = mock.Mock(status_code=200, content=b"not a zip")

        with TemporaryDirectory() as tmp, self.assertRaises(OrthancUnavailable):
            OrthancClient().download_study("abc", Path(tmp))

    @mock.patch("patients.orthanc_client.requests.get")
    def test_download_study_rejects_paths_outside_dest(self, get):
        get.return_value = mock.Mock(status_code=200, content=_zip({"../evil.dcm": b"x"}))

        with TemporaryDirectory() as tmp, self.assertRaises(OrthancUnavailable):
            OrthancClient().download_study("abc", Path(tmp) / "dicom")

    @mock.patch("patients.orthanc_client.requests.post")
    def test_upload_dicom_file_posts_dicom(self, post):
        post.return_value = _response({"ID": "inst"})

        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "seg.dcm"
            path.write_bytes(b"DICM")
            result = OrthancClient().upload_dicom_file(path)

        self.assertEqual(result, {"ID": "inst"})
        self.assertTrue(post.call_args.args[0].endswith("/instances"))
        self.assertEqual(post.call_args.kwargs["data"], b"DICM")
        self.assertEqual(post.call_args.kwargs["headers"]["Content-Type"], "application/dicom")
