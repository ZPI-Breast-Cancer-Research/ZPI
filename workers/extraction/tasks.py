"""Celery entry point of the extraction worker: runs the pipeline and saves the result in the
columns of the backend's ``reports`` row (docs/database.md). The only file of the module that
needs Django."""

import dataclasses
import json
import logging
import tempfile
from functools import cache
from pathlib import Path

from common.storage import BUCKET_REPORTS, download_file
from config.celery import app
from django.db import transaction
from django.utils import timezone
from extraction.models import ExtractionResult as ExtractionRow
from extraction.models import FailedStepChoices, SourceChoices, StatusChoices
from mlops.models import ModelVersion

from .config import Settings
from .documents import Document
from .pipeline import Extractor
from .schema import ExtractionResult

logger = logging.getLogger(__name__)

# A doctor may already have worked on the other statuses; a late or repeated task leaves them.
RUNNABLE = (StatusChoices.PENDING, StatusChoices.PROCESSING, StatusChoices.FAILED)


# what the pipeline reports when the OCR step failed (pipeline.extract_from_images)
OCR_FAILURE = "OCR:"
# settings of an OCR version that are not options of the engine itself
OCR_SETTINGS = ("lang", "orientation")


def _extractor(ocr: ModelVersion | None) -> Extractor:
    """The extractor reading pages the way the OCR version in use says.

    Without a version (a database without one) the OCR_* variables decide, as before.
    """
    if ocr is None:
        return _cached_extractor("", "{}")
    return _cached_extractor(ocr.ocr_engine, json.dumps(ocr.ocr_settings or {}, sort_keys=True))


@cache
def _cached_extractor(engine: str, settings_json: str) -> Extractor:
    # One per OCR configuration and worker process: loading the OCR models takes a while.
    settings = Settings.from_env()
    ocr_settings = json.loads(settings_json)
    if engine:
        settings = dataclasses.replace(
            settings,
            ocr_engine=engine,
            ocr_lang=ocr_settings.get("lang", settings.ocr_lang),
            ocr_orientation=ocr_settings.get("orientation", settings.ocr_orientation),
        )
    options = {key: value for key, value in ocr_settings.items() if key not in OCR_SETTINGS}
    return Extractor.from_settings(settings, ocr_options=options)


@app.task(name="extraction.run")
def run(keys: list[str], extraction_id: int | None = None, source: str | None = None) -> dict:
    """Extract the report stored under ``keys`` (one key per page) and save the result.

    ``extraction_id`` is the backend row created at upload. Without it (e.g. a manual call) the
    result is only returned. The return value is informational: there is no result backend.
    """
    ocr = _production_version(ModelVersion.ModuleChoices.OCR)
    if extraction_id is not None and not _start(extraction_id, ocr):
        return {"status": "skipped", "extraction_id": extraction_id}

    try:
        result = _extract(keys, source, ocr)
    except Exception as exc:
        # Download or an unexpected bug; the pipeline itself turns OCR/LLM errors into results.
        logger.exception("Extraction %s failed", extraction_id)
        reason = f"{type(exc).__name__}: {exc}"
        if extraction_id is not None:
            _save_failure(extraction_id, reason)
        return {"status": "error", "error": reason, "extraction_id": extraction_id}

    dumped = result.model_dump(mode="json")
    if extraction_id is not None:
        _save(extraction_id, result)
    return dumped


def _extract(keys: list[str], source: str | None, ocr: ModelVersion | None) -> ExtractionResult:
    with tempfile.TemporaryDirectory() as tmp:
        paths = [
            download_file(BUCKET_REPORTS, key, Path(tmp) / f"{i:03d}{Path(key).suffix}")
            for i, key in enumerate(keys)
        ]
        document = Document(source or Path(keys[0]).name, paths)
        return _extractor(ocr).extract(document)


def _start(extraction_id: int, ocr: ModelVersion | None) -> bool:
    """Mark the row PROCESSING and pin the versions in use; False when it must not run."""
    with transaction.atomic():
        row = ExtractionRow.objects.select_for_update().filter(id=extraction_id).first()
        if row is None:
            logger.warning("Extraction %s: no such row (deleted?), skipped", extraction_id)
            return False
        if row.status not in RUNNABLE:
            logger.info("Extraction %s: status %s, skipped", extraction_id, row.status)
            return False
        row.status = StatusChoices.PROCESSING
        row.model = _production_version(ModelVersion.ModuleChoices.EXT)
        # a text report is not read by OCR
        row.ocr_model = ocr if row.source == SourceChoices.SCAN else None
        # a retry must not show the previous attempt's result while it runs
        for field, value in _EMPTY_RESULT.items():
            setattr(row, field, value)
        row.save(update_fields=["status", "model", "ocr_model", *_EMPTY_RESULT, "updated_at"])
    return True


# the columns a run writes, as they are before it
_EMPTY_RESULT = {
    "error": "",
    "failed_step": "",
    "uncertainty": None,
    "generated_report": None,
    "warnings": [],
    "ocr_text": "",
    "ocr_confidence": None,
    "ocr_seconds": None,
    "ocr_engine_version": "",
    "page_rotations": [],
    "llm_seconds": None,
    "attempts": 0,
    "schema_version": "",
}


def _production_version(module: str) -> ModelVersion | None:
    """The version of the module in use when the task starts, or None.

    None keeps the extraction running (e.g. a database without seeded versions).
    """
    version = (
        ModelVersion.objects.filter(module=module, status=ModelVersion.StatusChoices.PRODUCTION)
        .order_by("-id")
        .first()
    )
    if version is None:
        logger.warning("No %s version in production; the report row does not point at one", module)
    return version


def _save(extraction_id: int, result: ExtractionResult) -> None:
    """The result goes to the columns of its step: OCR, then LLM (docs/database.md)."""
    provenance = result.provenance
    fields = {
        # OCR step (the text also for a .txt report: it is what the LLM read)
        "ocr_text": result.text,
        "ocr_confidence": provenance.ocr_mean_confidence,
        "ocr_seconds": result.ocr_seconds,
        "ocr_engine_version": provenance.ocr_engine_version or "",
        "page_rotations": provenance.page_rotations,
        # LLM step
        "warnings": result.warnings,
        "llm_seconds": result.llm_seconds,
        "attempts": result.attempts,
        "schema_version": provenance.schema_version,
        # the column the review queue sorts by
        "uncertainty": result.uncertainty,
    }
    if result.status == "ok" and result.data is not None:
        fields |= {
            "status": StatusChoices.COMPLETED,
            "generated_report": result.data.model_dump(mode="json"),
            "error": "",
            "failed_step": "",
        }
    else:
        error = result.error or "unknown error"
        failed = FailedStepChoices.OCR if error.startswith(OCR_FAILURE) else FailedStepChoices.LLM
        fields |= {"status": StatusChoices.FAILED, "error": error, "failed_step": failed}
    _update_processing(extraction_id, fields)


def _save_failure(extraction_id: int, reason: str) -> None:
    # Failed before OCR (e.g. the download), so no step; no result to judge, so the doctor
    # must look at it: maximum uncertainty
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
