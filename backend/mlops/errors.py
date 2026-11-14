"""Errors of talking to MLflow."""

from common.errors import AppError


class MlflowUnavailable(AppError):
    """MLflow could not be reached or returned an unusable response."""

    code = "mlflow_unavailable"
    status_code = 503
    detail = "MLflow jest niedostępny."
