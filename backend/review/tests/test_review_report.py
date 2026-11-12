"""The review screens get the report in the shape the frontend reads (review/extraction.ts)."""

from unittest import mock

import pytest
from django.urls import reverse
from extraction.models import ExtractionResult, StatusChoices
from segmentation.models import SegmentationResult

RESULT = {"status": "ok", "text": "Opis badania: zmiana w KGZ.", "data": {"zmiany": []}}


def _get(client, study, name):
    with mock.patch("review.views.OrthancClient") as orthanc:
        orthanc.return_value.list_studies.return_value = []
        return client.get(reverse(name, kwargs={"study_id": study.orthanc_path}))


@pytest.mark.django_db
def test_case_detail_returns_the_worker_result_with_the_ocr_text(authenticated_client, study):
    # Arrange
    ExtractionResult.objects.create(
        study=study, status=StatusChoices.COMPLETED, report_path="reports/a/opis.jpg", result=RESULT
    )

    # Act
    response = _get(authenticated_client, study, "review-case-detail")

    # Assert
    scan_url = reverse("review-report-scan", kwargs={"study_id": study.orthanc_path})
    assert response.data["report"] == {"originalUrl": scan_url, "result": RESULT}


@pytest.mark.django_db
@pytest.mark.parametrize("status_", [StatusChoices.PENDING, StatusChoices.PROCESSING])
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
def test_case_detail_shows_a_failure_before_extraction_as_an_error(authenticated_client, study):
    # Arrange: e.g. the file could not be downloaded, so the worker stored no result
    ExtractionResult.objects.create(
        study=study, status=StatusChoices.FAILED, error="download failed", result=None
    )

    # Act
    response = _get(authenticated_client, study, "review-case-detail")

    # Assert
    result = response.data["report"]["result"]
    assert (result["status"], result["error"], result["text"]) == ("error", "download failed", "")


@pytest.mark.django_db
def test_case_detail_without_a_report(authenticated_client, study):
    response = _get(authenticated_client, study, "review-case-detail")

    assert response.data["report"] is None


@pytest.mark.django_db
def test_approved_form_reaches_the_overview(authenticated_client, study):
    # Arrange
    SegmentationResult.objects.create(study=study, status=StatusChoices.APPROVED)
    ExtractionResult.objects.create(study=study, status=StatusChoices.COMPLETED, result=RESULT)
    form = {
        "report": {"zmiany": [{"birads": "5"}]},
        "lesions": {"0": {"birads": {"value": "5", "state": "corrected"}}},
    }

    # Act
    approved = authenticated_client.post(
        reverse("approve-form", kwargs={"study_id": study.orthanc_path}), form, format="json"
    )
    response = _get(authenticated_client, study, "review-overview")

    # Assert
    assert approved.status_code == 200
    assert response.data["report"] == {
        "source": {"originalUrl": None, "result": RESULT},  # no uploaded file
        "accepted": form["report"],
        "lesions": form["lesions"],
    }
