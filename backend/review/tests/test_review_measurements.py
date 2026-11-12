"""The review screens show the measurements the worker stored for the model mask."""

from unittest import mock

import pytest
from django.urls import reverse
from extraction.models import ExtractionResult, StatusChoices
from segmentation.models import SegmentationResult

MEASURED = {"volume_ml": 3.25, "dimensions_mm": [24.0, 18.5, 12.0]}
REPORT = {"zmiany": [{"birads": "4C", "wymiary": {"wartosci": [1.2, 2.1], "jednostka": "cm"}}]}


def _get(client, study, name):
    with mock.patch("review.views.OrthancClient") as orthanc:
        orthanc.return_value.list_studies.return_value = []
        return client.get(reverse(name, kwargs={"study_id": study.orthanc_path}))


@pytest.mark.django_db
def test_case_detail_shows_the_mask_measurements_and_the_size_in_the_report(
    authenticated_client, study
):
    # Arrange
    SegmentationResult.objects.create(
        study=study, status=StatusChoices.COMPLETED, measurements=MEASURED
    )
    ExtractionResult.objects.create(
        study=study, status=StatusChoices.COMPLETED, generated_report=REPORT
    )

    # Act
    response = _get(authenticated_client, study, "review-case-detail")

    # Assert
    assert response.data["measurements"] == {"volume": 3.25, "size": 24.0, "sizeInReport": 21.0}


@pytest.mark.django_db
def test_case_detail_without_measurements_shows_none(authenticated_client, study):
    # Arrange
    SegmentationResult.objects.create(study=study, status=StatusChoices.PROCESSING)

    # Act
    response = _get(authenticated_client, study, "review-case-detail")

    # Assert
    assert response.data["measurements"] == {"volume": None, "size": None, "sizeInReport": None}


@pytest.mark.django_db
def test_overview_shows_the_measurements_of_an_approved_mask(authenticated_client, study):
    # Arrange
    SegmentationResult.objects.create(
        study=study, status=StatusChoices.APPROVED, measurements=MEASURED
    )

    # Act
    response = _get(authenticated_client, study, "review-overview")

    # Assert
    assert response.data["measurements"] == {
        "volume": 3.25,
        "dimensions": [24.0, 18.5, 12.0],
        "intensity": None,
    }
    largest = next(r for r in response.data["comparison"] if r["feature"] == "largestSize")
    assert largest["fromMask"] == 24.0


@pytest.mark.django_db
def test_overview_of_a_corrected_mask_has_no_measurements_yet(authenticated_client, study):
    # Arrange: the stored measurements belong to the model mask, not to the correction (#25)
    SegmentationResult.objects.create(
        study=study, status=StatusChoices.CORRECTED, measurements=MEASURED
    )

    # Act
    response = _get(authenticated_client, study, "review-overview")

    # Assert
    assert response.data["measurements"]["volume"] is None
    assert response.data["measurements"]["dimensions"] is None
