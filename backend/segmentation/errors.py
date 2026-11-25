"""Errors of the segmentation app, reported by common/exception_handler.py as {"code", "detail"}."""

from common.errors import AppError


class NotApprovable(AppError):
    """The mask is not waiting for review (still running, failed, already approved or missing)."""

    code = "not_approvable"
    status_code = 409
    detail = "Tej maski nie można teraz zatwierdzić. Odśwież przypadek."
