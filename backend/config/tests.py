from unittest import mock
import pytest
from unittest.mock import patch

import requests
from django.db import OperationalError
from django.test import TestCase
from rest_framework.test import APIClient
from rest_framework import status
from users.models import Role, User
from users.permissions import PERMISSIONS

class HealthTests(TestCase):
    url = "/api/health"

    def setUp(self):
        self.client = APIClient()

    @mock.patch("patients.orthanc_client.requests.get")
    @mock.patch("common.storage.is_avaible", return_value=True)
    @mock.patch("config.views.MlflowClient.status", return_value="ok")
    def test_all_ok(self, mock_mlflow, mock_storage, mock_get):
        mock_get.return_value = mock.Mock(status_code=200, json=mock.Mock(return_value={}))

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json(),
            {"status": "ok", "database": "ok", "orthanc": "ok", "mlflow": "ok", "storage": "ok"},
        )
        self.assertTrue(mock_get.call_args.args[0].endswith("/system"))

    @mock.patch("patients.orthanc_client.requests.get")
    @mock.patch("common.storage.is_avaible", return_value=True)
    @mock.patch("config.views.MlflowClient.status", return_value="ok")
    def test_orthanc_unreachable_is_still_200(self, mock_mlflow, mock_storage, mock_get):
        mock_get.side_effect = requests.ConnectTimeout("timed out")

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "ok")
        self.assertEqual(response.json()["orthanc"], "unreachable")

    @mock.patch("patients.orthanc_client.requests.get")
    @mock.patch("common.storage.is_avaible", return_value=True)
    @mock.patch("config.views.MlflowClient.status", return_value="ok")
    def test_orthanc_unauthorized_is_reported(self, mock_mlflow, mock_storage, mock_get):
        mock_get.return_value = mock.Mock(status_code=401)

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "ok")
        self.assertEqual(response.json()["orthanc"], "unauthorized")

    @mock.patch("config.views.connection.cursor")
    @mock.patch("patients.orthanc_client.requests.get")
    @mock.patch("common.storage.is_avaible", return_value=True)
    @mock.patch("config.views.MlflowClient.status", return_value="ok")
    def test_database_down_is_503(self, mock_mlflow, mock_storage, mock_get, mock_cursor):
        mock_cursor.side_effect = OperationalError("db down")
        mock_get.side_effect = requests.ConnectionError("refused")

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json()["database"], "error")

    @mock.patch("patients.orthanc_client.requests.get")
    @mock.patch("common.storage.is_avaible", return_value=True)
    @mock.patch("config.views.MlflowClient.status")
    def test_mlflow_unreachable_is_still_200(self, mock_mlflow, mock_storage, mock_get):
        mock_get.return_value = mock.Mock(status_code=200, json=mock.Mock(return_value={}))
        mock_mlflow.return_value = "unreachable"

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["mlflow"], "unreachable")

@pytest.mark.django_db
class TestOrthancAuthEndpoint:
    url = "/api/auth/orthanc"
    permission = "review" 
    client = APIClient()

    def test_unauthenticated_gets_401(self):
        resp = self.client.get(self.url)
 
        assert resp.status_code == status.HTTP_401_UNAUTHORIZED
 
    @pytest.mark.parametrize("role", list(Role))
    def test_access_by_role(self, role):
        user = User.objects.create_user(username=f"user_{role.value}", password="x", role=role)
        self.client.force_authenticate(user=user)
 
        resp = self.client.get(self.url)
 
        if role.value in PERMISSIONS[self.permission]:
            assert resp.status_code == status.HTTP_204_NO_CONTENT
        else:
            assert resp.status_code == status.HTTP_403_FORBIDDEN
