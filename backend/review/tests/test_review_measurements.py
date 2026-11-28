"""The review screens show the measurements the worker stored for the mask on screen."""

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
        "source": "approved",
        "largest": {
            "sizeMm": 24.0,
            "volumeMl": 3.25,
        },  # stored before the largest part was measured
        "totalMl": 3.25,
    }
    largest = next(r for r in response.data["comparison"] if r["feature"] == "largestSize")
    assert largest["fromMask"] == 24.0


@pytest.mark.django_db
def test_overview_of_a_correction_being_saved_shows_the_models_numbers_and_says_so(
    authenticated_client, study
):
    # Arrange: the worker has not converted the SEG yet, the numbers are the model mask's
    SegmentationResult.objects.create(
        study=study, status=StatusChoices.CORRECTED, measurements=MEASURED
    )

    # Act
    response = _get(authenticated_client, study, "review-overview")

    # Assert
    assert response.data["status"] == "saving"
    assert response.data["measurements"]["source"] == "model"
    assert response.data["measurements"]["totalMl"] == 3.25


@pytest.mark.django_db
def test_overview_of_a_saved_correction_shows_its_own_numbers(authenticated_client, study):
    # Arrange: the worker stored the corrected mask and measured it (ADR 0004)
    SegmentationResult.objects.create(
        study=study,
        status=StatusChoices.CORRECTED,
        accepted_path="1/study_1_corrected.nii.gz",
        measurements=MEASURED,
    )

    # Act
    response = _get(authenticated_client, study, "review-overview")

    # Assert
    assert response.data["status"] == "verified"
    assert response.data["measurements"]["source"] == "approved"
    assert response.data["measurements"]["totalMl"] == 3.25
    largest = next(r for r in response.data["comparison"] if r["feature"] == "largestSize")
    assert largest["fromMask"] == 24.0


@pytest.mark.django_db
def test_case_detail_of_a_correction_being_saved_shows_no_mask_measurements(
    authenticated_client, study
):
    SegmentationResult.objects.create(
        study=study, status=StatusChoices.CORRECTED, measurements=MEASURED
    )

    response = _get(authenticated_client, study, "review-case-detail")

    assert response.data["measurements"]["volume"] is None
    assert response.data["measurements"]["size"] is None


@pytest.mark.django_db
def test_case_detail_of_a_saved_correction_shows_its_measurements(authenticated_client, study):
    SegmentationResult.objects.create(
        study=study,
        status=StatusChoices.CORRECTED,
        accepted_path="1/study_1_corrected.nii.gz",
        measurements=MEASURED,
    )

    response = _get(authenticated_client, study, "review-case-detail")

    assert response.data["measurements"]["volume"] == 3.25
    assert response.data["measurements"]["size"] == 24.0


@pytest.mark.django_db
def test_overview_tells_the_largest_part_from_all_parts(authenticated_client, study):
    # Arrange
    measured = {"volume_ml": 3.25, "largest_volume_ml": 2.9, "dimensions_mm": [24.0, 18.5, 12.0]}
    SegmentationResult.objects.create(
        study=study, status=StatusChoices.APPROVED, measurements=measured
    )

    # Act
    response = _get(authenticated_client, study, "review-overview")

    # Assert
    assert response.data["measurements"]["largest"] == {"sizeMm": 24.0, "volumeMl": 2.9}
    assert response.data["measurements"]["totalMl"] == 3.25


@pytest.mark.django_db
def test_overview_without_measurements_shows_none(authenticated_client, study):
    SegmentationResult.objects.create(study=study, status=StatusChoices.APPROVED)

    response = _get(authenticated_client, study, "review-overview")

    assert response.data["measurements"] is None
