"""The one way to approve a model mask and to take the approval back.

Used by review/views.py (approve_case, approve_mask, reopen_case, unapprove_mask). The caller
holds the row lock (select_for_update inside transaction.atomic) and writes the audit entry in the
same transaction. A NotApprovable raised here leaves the view, common/exception_handler.py answers
409 and rolls the transaction back, so a case is never half approved.
"""

from io import BytesIO

import pydicom
from celery import current_app
from django.db import transaction
from django.utils import timezone
from patients.orthanc_client import OrthancClient
from pydicom.errors import InvalidDicomError

from .errors import InvalidSeg, NotApprovable, SegFromOtherStudy
from .models import SegmentationResult, StatusChoices

CONVERT_TASK = "segmentation.correction_from_dicom_seg"

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


def approve_corrected_seg(study, user, seg_bytes: bytes) -> SegmentationResult:
    """Approve the mask corrected in the viewer, sent as a DICOM SEG (ADR 0004).

    1. The file must be a DICOM SEG of this study; the worker checks the geometry later
       (Frame of Reference, the pre phase as the referenced series).
    2. The mask must wait for review, checked before the upload so a refused approval does not
       leave a SEG in Orthanc.
    3. The SEG goes to Orthanc before the database changes: if Orthanc is down nothing is saved
       and the radiologist can try again. If another approval wins the race in step 4, the SEG
       stays in Orthanc unreferenced, which is harmless.
    4. Under the row lock: approve as CORRECTED, keep the SEG UIDs, queue the conversion after
       the commit (segmentation.correction_from_dicom_seg fills accepted_path and measurements).

    The caller may wrap this in its own transaction.atomic() to add the audit entry; the task is
    then queued when that outer transaction commits.
    """
    seg = _read_seg(seg_bytes)

    current = SegmentationResult.objects.filter(study=study).first()
    if current is None or current.status != StatusChoices.COMPLETED:
        # approve_mask raises the same error with the reason for the log
        approve_mask(current, user, corrected=True)
    if not study.orthanc_path:
        raise NotApprovable(f"study {study.pk} is not in Orthanc")

    orthanc = OrthancClient()
    if seg.StudyInstanceUID != orthanc.study_instance_uid(study.orthanc_path):
        raise SegFromOtherStudy(f"SEG {seg.SeriesInstanceUID} is not from study {study.pk}")
    orthanc.upload_dicom_bytes(seg_bytes)

    with transaction.atomic():
        result = SegmentationResult.objects.select_for_update().filter(study=study).first()
        approve_mask(result, user, corrected=True)
        result.approved_seg_series_uid = seg.SeriesInstanceUID
        result.approved_seg_sop_uid = seg.SOPInstanceUID
        result.error = ""
        result.save(update_fields=["approved_seg_series_uid", "approved_seg_sop_uid", "error"])
        result_id = result.pk
        transaction.on_commit(
            lambda: current_app.send_task(CONVERT_TASK, kwargs={"result_id": result_id})
        )
    return result


def _read_seg(seg_bytes: bytes):
    """The SEG's header (pixels are read by the worker); InvalidSeg when it is not one."""
    try:
        seg = pydicom.dcmread(BytesIO(seg_bytes), stop_before_pixels=True)
    except (InvalidDicomError, EOFError, ValueError) as exc:
        raise InvalidSeg(f"not a DICOM file: {exc}") from exc
    if seg.get("Modality") != "SEG":
        raise InvalidSeg(f"modality {seg.get('Modality')!r}, not SEG")
    for keyword in ("StudyInstanceUID", "SeriesInstanceUID", "SOPInstanceUID"):
        if not seg.get(keyword):
            raise InvalidSeg(f"no {keyword}")
    return seg


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
