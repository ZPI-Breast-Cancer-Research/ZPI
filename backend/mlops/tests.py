from unittest import mock

import requests
from django.test import SimpleTestCase

from .mlflow_client import MlflowClient, MlflowUnavailable

ALIAS_URL = "http://mlflow.test:5000/api/2.0/mlflow/registered-models/alias"


def _response(payload=None, status_code=200):
    response = mock.Mock(status_code=status_code)
    response.json.return_value = payload
    if status_code >= 400:
        response.raise_for_status.side_effect = requests.HTTPError(f"{status_code} error")
    return response


@mock.patch("mlops.mlflow_client.requests.request")
class MlflowClientTests(SimpleTestCase):
    def setUp(self):
        self.client = MlflowClient(base_url="http://mlflow.test:5000/")

    def test_status_ok(self, request):
        request.return_value = _response()

        self.assertEqual(self.client.status(), "ok")
        self.assertEqual(request.call_args.args, ("GET", "http://mlflow.test:5000/health"))

    def test_status_unreachable(self, request):
        request.side_effect = requests.ConnectionError("refused")

        self.assertEqual(self.client.status(), "unreachable")

    def test_set_alias_defaults_to_champion(self, request):
        request.return_value = _response({})

        self.client.set_alias("nnunet-breast", 3)

        self.assertEqual(request.call_args.args, ("POST", ALIAS_URL))
        self.assertEqual(
            request.call_args.kwargs["json"],
            {"name": "nnunet-breast", "alias": "champion", "version": "3"},
        )

    def test_version_by_alias(self, request):
        request.return_value = _response(
            {"model_version": {"name": "nnunet-breast", "version": "2"}}
        )

        version = self.client.version_by_alias("nnunet-breast", "challenger")

        self.assertEqual(version["version"], "2")
        self.assertEqual(
            request.call_args.kwargs["params"], {"name": "nnunet-breast", "alias": "challenger"}
        )

    def test_http_error_raises(self, request):
        request.return_value = _response(status_code=404)

        with self.assertRaises(MlflowUnavailable):
            self.client.version_by_alias("missing")

    def test_unexpected_payload_raises(self, request):
        request.return_value = _response({"unexpected": True})

        with self.assertRaises(MlflowUnavailable):
            self.client.version_by_alias("nnunet-breast")
