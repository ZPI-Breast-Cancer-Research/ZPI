"""Where the review screen finds the masks: DICOM SEG objects in Orthanc (ADR 0003)."""

from unittest import mock

import pytest
from django.urls import reverse
from extraction.models import StatusChoices
from rest_framework import status
from segmentation.models import SegmentationResult

STUDY_UID = "1.2.3.4"
MODEL_SEG = {"studyUid": STUDY_UID, "seriesUid": "1.2.3.4.10", "sopUid": "1.2.3.4.10.1"}
APPROVED_SEG = {"studyUid": STUDY_UID, "seriesUid": "1.2.3.4.20", "sopUid": "1.2.3.4.20.1"}


def _result(study, status_, model_seg=True, approved_seg=False):
    return SegmentationResult.objects.create(
        study=study,
        status=status_,
        model_seg_series_uid=MODEL_SEG["seriesUid"] if model_seg else "",
        model_seg_sop_uid=MODEL_SEG["sopUid"] if model_seg else "",
        approved_seg_series_uid=APPROVED_SEG["seriesUid"] if approved_seg else "",
        approved_seg_sop_uid=APPROVED_SEG["sopUid"] if approved_seg else "",
    )


def _get(client, study, name):
    with mock.patch("review.views.OrthancClient") as orthanc:
        orthanc.return_value.list_studies.return_value = [
            {"orthanc_id": study.orthanc_path, "study_instance_uid": STUDY_UID}
        ]
        return client.get(reverse(name, kwargs={"study_id": study.orthanc_path}))


@pytest.mark.django_db
def test_case_detail_points_to_the_model_seg(authenticated_client, study):
    # Arrange
    _result(study, StatusChoices.COMPLETED)

    # Act
    response = _get(authenticated_client, study, "review-case-detail")

    # Assert
    assert response.status_code == status.HTTP_200_OK
    assert response.data["mask"] == MODEL_SEG


@pytest.mark.django_db
@pytest.mark.parametrize(
    "status_",
    [StatusChoices.PROCESSING, StatusChoices.REJECTED, StatusChoices.COMPLETED],
    ids=["processing", "rejected", "empty-mask"],
)
def test_case_detail_has_no_mask_without_a_seg(authenticated_client, study, status_):
    # Arrange
    _result(study, status_, model_seg=False)

    # Act
    response = _get(authenticated_client, study, "review-case-detail")

    # Assert
    assert response.data["mask"] is None


@pytest.mark.django_db
def test_case_detail_has_no_mask_when_orthanc_does_not_know_the_study(authenticated_client, study):
    # Arrange
    _result(study, StatusChoices.COMPLETED)

    # Act
    with mock.patch("review.views.OrthancClient") as orthanc:
        orthanc.return_value.list_studies.return_value = []
        response = authenticated_client.get(
            reverse("review-case-detail", kwargs={"study_id": study.orthanc_path})
        )

    # Assert
    assert response.data["mask"] is None


@pytest.mark.django_db
def test_overview_points_to_the_model_and_the_approved_seg(authenticated_client, study):
    # Arrange
    _result(study, StatusChoices.CORRECTED, approved_seg=True)

    # Act
    response = _get(authenticated_client, study, "review-overview")

    # Assert
    assert response.status_code == status.HTTP_200_OK
    assert response.data["masks"] == {"approved": APPROVED_SEG, "model": MODEL_SEG}


@pytest.mark.django_db
def test_overview_of_a_mask_approved_without_changes_shows_the_model_seg(
    authenticated_client, study
):
    # Arrange
    _result(study, StatusChoices.APPROVED)

    # Act
    response = _get(authenticated_client, study, "review-overview")

    # Assert
    assert response.data["masks"] == {"approved": MODEL_SEG, "model": MODEL_SEG}


@pytest.mark.django_db
def test_overview_of_a_corrected_mask_has_no_approved_seg_until_it_is_stored(
    authenticated_client, study
):
    # Arrange
    _result(study, StatusChoices.CORRECTED)

    # Act
    response = _get(authenticated_client, study, "review-overview")

    # Assert
    assert response.data["masks"] == {"approved": None, "model": MODEL_SEG}
