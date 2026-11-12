import pytest
from unittest import mock
from django.urls import reverse
from rest_framework import status

from patients.models import Study
from segmentation.models import SegmentationResult
from extraction.models import StatusChoices


@pytest.mark.django_db
def test_review_queue_returns_empty_list(authenticated_client):
    with mock.patch("review.views.OrthancClient") as orthanc:
        orthanc.return_value.list_studies.return_value = []

        response = authenticated_client.get(
            reverse("review-queue")
        )

    assert response.status_code == status.HTTP_200_OK
    assert response.data == []


@pytest.mark.django_db
def test_review_queue_returns_studies_with_completed_segmentation(
    authenticated_client,
    study,
    segmentation,
):
    with mock.patch("review.views.OrthancClient") as orthanc:
        orthanc.return_value.list_studies.return_value = [
            {
                "orthanc_id": study.orthanc_path,
                "study_date": "20261026",
            }
        ]

        response = authenticated_client.get(
            reverse("review-queue")
        )

    assert response.status_code == status.HTTP_200_OK
    assert len(response.data) == 1

    item = response.data[0]

    assert item["studyId"] == study.orthanc_path
    assert item["studyNumber"] == str(study.id).zfill(4)
    assert item["studyDate"] == "2026-10-26"
    assert item["uncertainty"] == 0.75


@pytest.mark.django_db
def test_review_queue_returns_studies_with_completed_extraction(
    authenticated_client,
    study,
    extraction,
):
    with mock.patch("review.views.OrthancClient") as orthanc:
        orthanc.return_value.list_studies.return_value = []

        response = authenticated_client.get(
            reverse("review-queue")
        )

    assert response.status_code == status.HTTP_200_OK
    assert len(response.data) == 1
    assert response.data[0]["studyId"] == study.orthanc_path
    assert response.data[0]["uncertainty"] == 0.45


@pytest.mark.django_db
def test_review_queue_sorts_by_uncertainty_descending(
    authenticated_client,
    study,
):
    second_study = Study.objects.create(
        orthanc_path="orthanc-study-456"
    )

    SegmentationResult.objects.create(
        study=study,
        status=StatusChoices.COMPLETED,
        uncertainty=0.2,
    )

    SegmentationResult.objects.create(
        study=second_study,
        status=StatusChoices.COMPLETED,
        uncertainty=0.9,
    )

    with mock.patch("review.views.OrthancClient") as orthanc:
        orthanc.return_value.list_studies.return_value = []

        response = authenticated_client.get(
            reverse("review-queue")
        )

    assert response.status_code == status.HTTP_200_OK
    assert len(response.data) == 2
    assert response.data[0]["studyId"] == second_study.orthanc_path
    assert response.data[1]["studyId"] == study.orthanc_path


@pytest.mark.django_db
def test_review_queue_uses_default_uncertainty_when_none(
    authenticated_client,
    study,
):
    SegmentationResult.objects.create(
        study=study,
        status=StatusChoices.COMPLETED,
        uncertainty=None,
    )

    with mock.patch("review.views.OrthancClient") as orthanc:
        orthanc.return_value.list_studies.return_value = []

        response = authenticated_client.get(
            reverse("review-queue")
        )

    assert response.status_code == status.HTTP_200_OK
    assert response.data[0]["uncertainty"] == 0.0


@pytest.mark.django_db
def test_review_queue_uses_placeholder_when_study_date_is_missing(
    authenticated_client,
    study,
    segmentation,
):
    with mock.patch("review.views.OrthancClient") as orthanc:
        orthanc.return_value.list_studies.return_value = [
            {"orthanc_id": study.orthanc_path}
        ]

        response = authenticated_client.get(
            reverse("review-queue")
        )

    assert response.status_code == status.HTTP_200_OK
    assert response.data[0]["studyDate"] == "----------"


@pytest.mark.django_db
def test_review_queue_requires_authentication(api_client):
    response = api_client.get(reverse("review-queue"))

    assert response.status_code in (
        status.HTTP_401_UNAUTHORIZED,
        status.HTTP_403_FORBIDDEN,
    )
