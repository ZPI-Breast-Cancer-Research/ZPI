"""When a report is processed and what may still change (docs/database.md, "Rules").

* Uploading a report computes nothing; processing starts on demand and when the report is
  assigned to a study.
* A verified mask or report form is never replaced; a result that is not verified is overwritten
  by a new run.
* A study is closed when both its mask and its active report form are verified; a closed study
  accepts no new report and no new run.
"""

from celery import current_app
from django.db import transaction
from segmentation.models import SegmentationResult

from .models import ExtractionResult, SourceChoices, StatusChoices

VERIFIED = (StatusChoices.APPROVED, StatusChoices.CORRECTED)
# a worker is on it
BUSY = (StatusChoices.PENDING, StatusChoices.PROCESSING)
# who may order a report to be processed again; a radiologist only after a failure
REPROCESS_ANY = ("researcher", "admin")


def is_closed(study) -> bool:
    """Both the mask and the active report form of the study are verified."""
    mask = SegmentationResult.objects.filter(study=study).first()
    if mask is None or mask.status not in VERIFIED:
        return False
    report = ExtractionResult.objects.filter(study=study).active()
    return report is not None and report.status in VERIFIED


def may_process(role: str | None, report: ExtractionResult) -> bool:
    """Whether the role may order this report to be processed (first time or again)."""
    if report.status == StatusChoices.UPLOADED:
        return True
    return role in REPROCESS_ANY or report.status == StatusChoices.FAILED


def start_processing(report: ExtractionResult, user) -> None:
    """Queue the report for OCR and extraction; the task is sent once the transaction commits.

    A previous result that is not verified is cleared here, so the screens never mix the old
    result with the new run. The caller checks the rules above first.
    """
    if report.source == SourceChoices.MANUAL or not report.report_path:
        raise ValueError(f"Report {report.pk} has no file to process")
    if report.status in VERIFIED:
        raise ValueError(f"Report {report.pk} is verified")

    report.status = StatusChoices.PENDING
    report.requested_by = user
    report.error = ""
    report.failed_step = ""
    report.ocr_model = None
    report.ocr_text = ""
    report.ocr_confidence = None
    report.ocr_seconds = None
    report.ocr_engine_version = ""
    report.page_rotations = []
    report.llm_seconds = None
    report.attempts = 0
    report.schema_version = ""
    report.warnings = []
    report.uncertainty = None
    report.generated_report = None
    report.accepted_report = None
    report.field_checks = None
    report.accepted_by = None
    report.accepted_at = None
    report.save()

    report_id, key = report.pk, report.report_path
    transaction.on_commit(
        lambda: current_app.send_task(
            "extraction.run", kwargs={"extraction_id": report_id, "keys": [key]}
        )
    )
