"""Errors of talking to MLflow."""

from common.errors import AppError


class MlflowUnavailable(AppError):
    """MLflow could not be reached or returned an unusable response."""

    code = "mlflow_unavailable"
    status_code = 503
    detail = "MLflow jest niedostępny."


class LlmServerUnavailable(AppError):
    """The LLM server of the extraction worker could not be asked for its models."""

    code = "llm_unavailable"
    status_code = 503
    detail = "Serwer modeli językowych jest niedostępny."
