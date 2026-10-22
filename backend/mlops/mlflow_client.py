import requests
from django.conf import settings

TIMEOUT = (2, 5)

ALIAS_CHAMPION = "champion"
ALIAS_CHALLENGER = "challenger"

_ALIAS_PATH = "/api/2.0/mlflow/registered-models/alias"


class MlflowUnavailable(Exception):
    pass


class MlflowClient:
    def __init__(self, base_url: str | None = None):
        self.base_url = (base_url or settings.MLFLOW_TRACKING_URI).rstrip("/")

    def _request(self, method: str, path: str, **kwargs) -> requests.Response:
        try:
            response = requests.request(
                method, f"{self.base_url}{path}", timeout=TIMEOUT, **kwargs
            )
            response.raise_for_status()
        except requests.RequestException as exc:
            raise MlflowUnavailable(f"MLflow request {path} failed: {exc}") from exc
        return response

    def status(self) -> str:
        try:
            self._request("GET", "/health")
        except MlflowUnavailable:
            return "unreachable"
        return "ok"

    def version_by_alias(self, model: str, alias: str = ALIAS_CHAMPION) -> dict:
        response = self._request("GET", _ALIAS_PATH, params={"name": model, "alias": alias})
        try:
            return response.json()["model_version"]
        except (ValueError, KeyError) as exc:
            raise MlflowUnavailable(f"MLflow {_ALIAS_PATH} returned an unexpected payload") from exc

    def set_alias(self, model: str, version: str | int, alias: str = ALIAS_CHAMPION) -> None:
        self._request(
            "POST", _ALIAS_PATH, json={"name": model, "alias": alias, "version": str(version)}
        )
