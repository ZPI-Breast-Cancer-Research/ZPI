from unittest import mock

import requests
from django.test import SimpleTestCase, override_settings
from rest_framework.test import APIClient

from .orthanc_client import OrthancClient

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
