"""The one way to approve a model mask and to take the approval back.

Used by review/views.py (approve_case, approve_mask, reopen_case, unapprove_mask). The caller
holds the row lock (select_for_update inside transaction.atomic) and writes the audit entry in the
same transaction. A NotApprovable raised here leaves the view, common/exception_handler.py answers
409 and rolls the transaction back, so a case is never half approved.
"""

from django.utils import timezone

from .errors import NotApprovable
from .models import SegmentationResult, StatusChoices

VERIFIED = (StatusChoices.APPROVED, StatusChoices.CORRECTED)

_APPROVAL_FIELDS = ["status", "accepted_by", "accepted_at", "accepted_path", "updated_at"]


def approve_mask(result: SegmentationResult | None, user, *, corrected: bool) -> SegmentationResult:
    """Approve the model mask that waits for review.

    corrected=False: the radiologist accepts the model mask as it is (APPROVED); the accepted
    mask is the model's file.
    corrected=True: the radiologist changed it (CORRECTED); the accepted file is filled in by the
    worker from the corrected SEG (segmentation.correction_from_dicom_seg, after T-06b).

    Raises NotApprovable when there is no result or it is not COMPLETED.
    """
    if result is None:
        raise NotApprovable("no segmentation result")
    if result.status != StatusChoices.COMPLETED:
        raise NotApprovable(f"result {result.pk} is {result.status}, not COMPLETED")

    result.status = StatusChoices.CORRECTED if corrected else StatusChoices.APPROVED
    result.accepted_by = user
    result.accepted_at = timezone.now().date()
    result.accepted_path = None if corrected else result.generated_path
    result.save(update_fields=_APPROVAL_FIELDS)
    return result


def approve_mask_in_case(result: SegmentationResult | None, user, *, corrected: bool) -> bool:
    """The mask part of approving the whole case (approve_case).

    A mask already approved on its own (approve-mask, then the form later) is not an error.
    True when this call approved it, False when it was approved before. Any other state
    (running, failed, no result) raises NotApprovable.
    """
    if result is not None and result.status in VERIFIED:
        return False
    approve_mask(result, user, corrected=corrected)
    return True


def reopen_mask(result: SegmentationResult | None) -> bool:
    """Take back the approval; the case returns to the queue. True when it changed.

    A mask that is not approved is left as it is (reopen_case also reopens the form, which may be
    the only approved part). Who approved before stays in the audit log. The approved SEG stays in
    Orthanc, but the result no longer points to it, so a conversion still running for it does not
    save its output (correction_from_dicom_seg checks approved_seg_series_uid).
    """
    if result is None or result.status not in VERIFIED:
        return False
    result.status = StatusChoices.COMPLETED
    result.accepted_by = None
    result.accepted_at = None
    result.accepted_path = None
    result.approved_seg_series_uid = ""
    result.approved_seg_sop_uid = ""
    result.save(
        update_fields=[*_APPROVAL_FIELDS, "approved_seg_series_uid", "approved_seg_sop_uid"]
    )
    return True
