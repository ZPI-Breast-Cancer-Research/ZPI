from unittest import mock

import pytest
from django.test import TestCase
from rest_framework.test import APIClient
from rest_framework import status

from users.models import Role, User
from users.permissions import PERMISSIONS


class HealthTests(TestCase):
    url = "/api/health"

    def setUp(self):
        self.client = APIClient()
        storage = mock.patch("config.views.is_avaible", return_value=True)
        storage.start()
        self.addCleanup(storage.stop)

    @mock.patch("config.views._database_ok", return_value=True)
    @mock.patch("config.views.OrthancClient.status", return_value="ok")
    @mock.patch("config.views.MlflowClient.status", return_value="ok")
    def test_all_ok(self, mock_mlflow, mock_orthanc, mock_database):
        response = self.client.get(self.url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)

        body = response.json()

        self.assertIn("checkedAt", body)
        self.assertIn("components", body)
        self.assertIn("profile", body)
        self.assertIn("retraining", body)

        components = {
            component["key"]: component
            for component in body["components"]
        }

        self.assertEqual(components["orthanc"]["state"], "ok")
        self.assertEqual(components["registry"]["state"], "ok")
        # nothing checks these yet, so they must not claim to be fine
        for key in ("pacs", "segmentation", "extraction", "training", "llm"):
            self.assertEqual(components[key]["state"], "unknown")
        # the PACS indicator and the container healthcheck read the top-level keys
        self.assertEqual(body["status"], "ok")
        self.assertEqual(body["orthanc"], "ok")

    @mock.patch("config.views._database_ok", return_value=True)
    @mock.patch("config.views.OrthancClient.status", return_value="unreachable")
    @mock.patch("config.views.MlflowClient.status", return_value="ok")
    def test_orthanc_unreachable_is_still_200(
        self,
        mock_mlflow,
        mock_orthanc,
        mock_database,
    ):
        response = self.client.get(self.url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)

        components = {
            component["key"]: component
            for component in response.json()["components"]
        }

        self.assertEqual(components["orthanc"]["state"], "down")

    @mock.patch("config.views._database_ok", return_value=True)
    @mock.patch("config.views.OrthancClient.status", return_value="unauthorized")
    @mock.patch("config.views.MlflowClient.status", return_value="ok")
    def test_orthanc_unauthorized_is_reported(
        self,
        mock_mlflow,
        mock_orthanc,
        mock_database,
    ):
        response = self.client.get(self.url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)

        components = {
            component["key"]: component
            for component in response.json()["components"]
        }

        self.assertEqual(components["orthanc"]["state"], "unknown")
        self.assertEqual(components["orthanc"]["detail"], "401")

    @mock.patch("config.views._database_ok", return_value=False)
    @mock.patch("config.views.OrthancClient.status", return_value="ok")
    @mock.patch("config.views.MlflowClient.status", return_value="ok")
    def test_database_down_is_503(
        self,
        mock_mlflow,
        mock_orthanc,
        mock_database,
    ):
        response = self.client.get(self.url)

        self.assertEqual(
            response.status_code,
            status.HTTP_503_SERVICE_UNAVAILABLE,
        )

        components = {
            component["key"]: component
            for component in response.json()["components"]
        }

        self.assertEqual(components["segmentation"]["state"], "down")
        self.assertEqual(components["extraction"]["state"], "down")

    @mock.patch("config.views._database_ok", return_value=True)
    @mock.patch("config.views.OrthancClient.status", return_value="ok")
    @mock.patch("config.views.MlflowClient.status", return_value="unreachable")
    def test_mlflow_unreachable_is_still_200(
        self,
        mock_mlflow,
        mock_orthanc,
        mock_database,
    ):
        response = self.client.get(self.url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)

        components = {
            component["key"]: component
            for component in response.json()["components"]
        }

        self.assertEqual(components["registry"]["state"], "down")


@pytest.mark.django_db
class TestOrthancAuthEndpoint:
    url = "/api/auth/orthanc"
    permission = "review"
    client = APIClient()

    def test_unauthenticated_gets_401(self):
        response = self.client.get(self.url)

        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    @pytest.mark.parametrize("role", list(Role))
    def test_access_by_role(self, role):
        user = User.objects.create_user(
            username=f"user_{role.value}",
            password="x",
            role=role,
        )

        self.client.force_authenticate(user=user)
        response = self.client.get(self.url)
        if role.value in PERMISSIONS[self.permission]:
            assert response.status_code == status.HTTP_204_NO_CONTENT
        else:
            assert response.status_code == status.HTTP_403_FORBIDDEN