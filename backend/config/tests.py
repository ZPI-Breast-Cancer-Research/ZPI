from unittest import mock

import requests
from django.db import OperationalError
from django.test import TestCase
from rest_framework.test import APIClient


@mock.patch("config.views.MlflowClient.status", return_value="ok")
class HealthTests(TestCase):
    url = "/api/health"

    def setUp(self):
        self.client = APIClient()

    @mock.patch("patients.orthanc_client.requests.get")
    def test_all_ok(self, get, _mlflow):
        get.return_value = mock.Mock(status_code=200, json=mock.Mock(return_value={}))

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json(),
            {"status": "ok", "database": "ok", "orthanc": "ok", "mlflow": "ok"},
        )
        self.assertTrue(get.call_args.args[0].endswith("/system"))

    @mock.patch("patients.orthanc_client.requests.get")
    def test_orthanc_unreachable_is_still_200(self, get, _mlflow):
        get.side_effect = requests.ConnectTimeout("timed out")

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "ok")
        self.assertEqual(response.json()["orthanc"], "unreachable")

    @mock.patch("patients.orthanc_client.requests.get")
    def test_orthanc_unauthorized_is_reported(self, get, _mlflow):
        get.return_value = mock.Mock(status_code=401)

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "ok")
        self.assertEqual(response.json()["orthanc"], "unauthorized")

    @mock.patch("patients.orthanc_client.requests.get")
    @mock.patch("config.views.connection.cursor", side_effect=OperationalError("db down"))
    def test_database_down_is_503(self, _cursor, get, _mlflow):
        get.side_effect = requests.ConnectionError("refused")

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json()["database"], "error")

    @mock.patch("patients.orthanc_client.requests.get")
    def test_mlflow_unreachable_is_still_200(self, get, mlflow):
        get.return_value = mock.Mock(status_code=200, json=mock.Mock(return_value={}))
        mlflow.return_value = "unreachable"

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["mlflow"], "unreachable")
