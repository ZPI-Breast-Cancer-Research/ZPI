"""Celery entry point of the extraction worker: runs the pipeline and saves the result in the
backend's ``ExtractionResult`` row. The only file of the module that needs Django."""

import logging
import tempfile
from functools import cache
from pathlib import Path

from common.storage import BUCKET_REPORTS, download_file
from config.celery import app
from django.db import transaction
from django.utils import timezone
from extraction.models import ExtractionResult as ExtractionRow
from extraction.models import StatusChoices
from mlops.models import ModelVersion

from .config import Settings
from .documents import Document
from .pipeline import Extractor
from .schema import ExtractionResult

logger = logging.getLogger(__name__)

# A doctor may already have worked on the other statuses; a late or repeated task leaves them.
RUNNABLE = (StatusChoices.PENDING, StatusChoices.PROCESSING, StatusChoices.FAILED)


@cache
def _extractor() -> Extractor:
    # One per worker process: loading the OCR models takes a while.
    return Extractor.from_settings(Settings.from_env())


@app.task(name="extraction.run")
def run(keys: list[str], extraction_id: int | None = None, source: str | None = None) -> dict:
    """Extract the report stored under ``keys`` (one key per page) and save the result.

    ``extraction_id`` is the backend row created at upload. Without it (e.g. a manual call) the
    result is only returned. The return value is informational: there is no result backend.
    """
    if extraction_id is not None and not _start(extraction_id):
        return {"status": "skipped", "extraction_id": extraction_id}

    try:
        result = _extract(keys, source)
    except Exception as exc:
        # Download or an unexpected bug; the pipeline itself turns OCR/LLM errors into results.
        logger.exception("Extraction %s failed", extraction_id)
        reason = f"{type(exc).__name__}: {exc}"
        if extraction_id is not None:
            _save_failure(extraction_id, reason)
        return {"status": "error", "error": reason, "extraction_id": extraction_id}

    dumped = result.model_dump(mode="json")
    if extraction_id is not None:
        _save(extraction_id, result, dumped)
    return dumped


def _extract(keys: list[str], source: str | None) -> ExtractionResult:
    with tempfile.TemporaryDirectory() as tmp:
        paths = [
            download_file(BUCKET_REPORTS, key, Path(tmp) / f"{i:03d}{Path(key).suffix}")
            for i, key in enumerate(keys)
        ]
        document = Document(source or Path(keys[0]).name, paths)
        return _extractor().extract(document)


def _start(extraction_id: int) -> bool:
    """Mark the row PROCESSING and pin the production model; False when it must not run."""
    with transaction.atomic():
        row = ExtractionRow.objects.select_for_update().filter(id=extraction_id).first()
        if row is None:
            logger.warning("Extraction %s: no such row (deleted?), skipped", extraction_id)
            return False
        if row.status not in RUNNABLE:
            logger.info("Extraction %s: status %s, skipped", extraction_id, row.status)
            return False
        row.status = StatusChoices.PROCESSING
        row.model = _production_model()
        row.error = ""
        # a retry must not show the previous attempt's result while it runs
        row.result = None
        row.uncertainty = None
        row.save(update_fields=["status", "model", "error", "result", "uncertainty", "updated_at"])
    return True


def _production_model() -> ModelVersion | None:
    """The extraction model version in production when the task starts, or None.

    None keeps the extraction running (e.g. a database without seeded model versions); the
    model that really produced the result is in ``provenance`` either way.
    """
    model = (
        ModelVersion.objects.filter(
            module=ModelVersion.ModuleChoices.EXT,
            status=ModelVersion.StatusChoices.PRODUCTION,
        )
        .order_by("-activated_at", "-id")
        .first()
    )
    if model is None:
        logger.warning("No production extraction model version; ExtractionResult.model left empty")
    return model


def _save(extraction_id: int, result: ExtractionResult, dumped: dict) -> None:
    # result: the whole ExtractionResult, also on error (the frontend shows its status and text);
    # generated_report: only the data, the shape the review form and mlops read.
    fields = {
        "result": dumped,
        "provenance": dumped["provenance"],
        "warnings": result.warnings,
        # the column the review queue sorts by
        "uncertainty": result.uncertainty,
    }
    if result.status == "ok" and result.data is not None:
        fields |= {
            "status": StatusChoices.COMPLETED,
            "generated_report": result.data.model_dump(mode="json"),
            "error": "",
        }
    else:
        fields |= {"status": StatusChoices.FAILED, "error": result.error or "unknown error"}
    _update_processing(extraction_id, fields)


def _save_failure(extraction_id: int, reason: str) -> None:
    # no result to judge, so the doctor must look at it: maximum uncertainty
    _update_processing(
        extraction_id, {"status": StatusChoices.FAILED, "error": reason, "uncertainty": 1.0}
    )


def _update_processing(extraction_id: int, fields: dict) -> None:
    # Only a row this task put in PROCESSING is updated, never one a doctor already reviewed.
    # QuerySet.update skips auto_now, so updated_at is set here.
    updated = ExtractionRow.objects.filter(
        id=extraction_id, status=StatusChoices.PROCESSING
    ).update(**fields, updated_at=timezone.now())
    if not updated:
        logger.warning(
            "Extraction %s: row changed while extracting, result not saved", extraction_id
        )
    else:
        logger.info("Extraction %s: %s", extraction_id, fields["status"])
