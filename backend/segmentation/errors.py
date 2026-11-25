"""Errors of the segmentation app, reported by common/exception_handler.py as {"code", "detail"}."""

from common.errors import AppError


class NotApprovable(AppError):
    """The mask is not waiting for review (still running, failed, already approved or missing)."""

    code = "not_approvable"
    status_code = 409
    detail = "Tej maski nie można teraz zatwierdzić. Odśwież przypadek."


class InvalidSeg(AppError):
    """The corrected mask sent by the viewer is not a DICOM SEG."""

    code = "invalid_seg"
    status_code = 400
    detail = "Przesłany plik nie jest maską DICOM SEG."


class SegFromOtherStudy(AppError):
    """The corrected mask belongs to another study than the one being approved."""

    code = "seg_wrong_study"
    status_code = 400
    detail = "Przesłana maska należy do innego badania."
