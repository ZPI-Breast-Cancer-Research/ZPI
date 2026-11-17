"""The review screens get the report in the shape the frontend reads (review/extraction.ts),
put together from the columns of the report row."""

from unittest import mock

import pytest
from django.urls import reverse
from extraction.models import ExtractionResult, SourceChoices, StatusChoices
from mlops.models import ModelVersion
from segmentation.models import SegmentationResult

DATA = {"zmiany": []}


def _get(client, study, name):
    with mock.patch("review.views.OrthancClient") as orthanc:
        orthanc.return_value.list_studies.return_value = []
        return client.get(reverse(name, kwargs={"study_id": study.orthanc_path}))


def _ocr_version() -> ModelVersion:
    """The first OCR version (mlops 0005); created here when a test flushed it away."""
    version, _ = ModelVersion.objects.get_or_create(
        module="ocr",
        version="1",
        defaults={
            "name": "ocr",
            "status": "production",
            "ocr_engine": "paddle",
            "ocr_settings": {"lang": "pl", "orientation": "paddle"},
        },
    )
    return version


def _read_scan(study, **fields) -> ExtractionResult:
    """A scan the worker has read: OCR columns, then LLM columns."""
    return ExtractionResult.objects.create(
        study=study,
        report_path="reports/a/opis.jpg",
        source=SourceChoices.SCAN,
        ocr_model=_ocr_version(),
        ocr_text="Opis badania: zmiana w KGZ.",
        ocr_confidence=0.91,
        ocr_seconds=1.5,
        ocr_engine_version="3.1",
        page_rotations=[90],
        generated_report=DATA,
        warnings=["zmiany.0.strona"],
        llm_seconds=4.0,
        attempts=1,
        schema_version="4",
        **fields,
    )


@pytest.mark.django_db
def test_case_detail_builds_the_worker_result_from_the_columns(authenticated_client, study):
    # Arrange
    _read_scan(study, status=StatusChoices.COMPLETED)

    # Act
    response = _get(authenticated_client, study, "review-case-detail")

    # Assert
    report = response.data["report"]
    assert report["originalUrl"] == reverse(
        "review-report-scan", kwargs={"study_id": study.orthanc_path}
    )
    result = report["result"]
    assert (result["status"], result["source"], result["data"]) == ("ok", "opis.jpg", DATA)
    assert result["text"] == "Opis badania: zmiana w KGZ."
    assert result["warnings"] == ["zmiany.0.strona"]
    assert (result["attempts"], result["ocr_seconds"], result["llm_seconds"]) == (1, 1.5, 4.0)
    assert result["provenance"] == {
        "ocr_engine": "paddle",  # from the OCR version (mlops 0005)
        "ocr_engine_version": "3.1",
        "ocr_mean_confidence": 0.91,
        "orientation_detector": "paddle",
        "page_rotations": [90],
        "llm_provider": "",
        "llm_model": "",
        "prompt_version": "",
        "schema_version": "4",
    }


@pytest.mark.django_db
@pytest.mark.parametrize(
    "status_", [StatusChoices.UPLOADED, StatusChoices.PENDING, StatusChoices.PROCESSING]
)
def test_case_detail_marks_a_report_without_a_result_as_pending(
    authenticated_client, study, status_
):
    # Arrange
    ExtractionResult.objects.create(study=study, status=status_, report_path="reports/a/opis.jpg")

    # Act
    response = _get(authenticated_client, study, "review-case-detail")

    # Assert
    assert response.data["report"] == "pending"


@pytest.mark.django_db
def test_case_detail_shows_a_failed_step(authenticated_client, study):
    # Arrange
    _read_scan(study, status=StatusChoices.FAILED, error="LLM: timeout", failed_step="llm")

    # Act
    response = _get(authenticated_client, study, "review-case-detail")

    # Assert
    result = response.data["report"]["result"]
    assert (result["status"], result["error"], result["failedStep"]) == (
        "error",
        "LLM: timeout",
        "llm",
    )
    assert result["data"] is None
    # the OCR text is still there to look at
    assert result["text"] == "Opis badania: zmiana w KGZ."


@pytest.mark.django_db
def test_case_detail_shows_a_failure_before_extraction_as_an_error(authenticated_client, study):
    # Arrange: e.g. the file could not be downloaded, so the worker stored no result
    ExtractionResult.objects.create(
        study=study, status=StatusChoices.FAILED, error="download failed"
    )

    # Act
    response = _get(authenticated_client, study, "review-case-detail")

    # Assert
    result = response.data["report"]["result"]
    assert (result["status"], result["error"], result["text"]) == ("error", "download failed", "")
    assert result["failedStep"] is None


@pytest.mark.django_db
def test_case_detail_without_a_report(authenticated_client, study):
    response = _get(authenticated_client, study, "review-case-detail")

    assert response.data["report"] is None


@pytest.mark.django_db
def test_approved_form_reaches_the_overview(authenticated_client, study):
    # Arrange
    SegmentationResult.objects.create(study=study, status=StatusChoices.APPROVED)
    _read_scan(study, status=StatusChoices.COMPLETED)
    form = {
        "report": {"zmiany": [{"birads": "5"}]},
        "fields": {"zmiany.0.birads": "corrected"},
    }

    # Act
    approved = authenticated_client.post(
        reverse("approve-form", kwargs={"study_id": study.orthanc_path}), form, format="json"
    )
    response = _get(authenticated_client, study, "review-overview")

    # Assert
    assert approved.status_code == 200
    report = response.data["report"]
    assert report["accepted"] == form["report"]
    # the model's answer stays next to the accepted form
    assert report["source"]["result"]["data"] == DATA
