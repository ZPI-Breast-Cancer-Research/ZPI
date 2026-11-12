import pytest
from unittest import mock
from django.urls import reverse
from django.utils import timezone
from rest_framework import status

from extraction.models import ExtractionResult, StatusChoices
from segmentation.models import SegmentationResult


@pytest.mark.django_db
def test_review_overview_returns_conflict_when_segmentation_is_not_verified(
    authenticated_client,
    study,
):
    SegmentationResult.objects.create(
        study=study,
        status=StatusChoices.COMPLETED,
    )

    response = authenticated_client.get(
        reverse(
            "review-overview",
            kwargs={"study_id": study.orthanc_path},
        )
    )

    assert response.status_code == status.HTTP_409_CONFLICT
    assert response.data["code"] == "not_verified"


@pytest.mark.django_db
def test_review_overview_returns_verified_case(
    authenticated_client,
    reviewer,
    study,
):
    SegmentationResult.objects.create(
        study=study,
        status=StatusChoices.APPROVED,
        accepted_by=reviewer,
        accepted_at=timezone.now().date(),
    )

    ExtractionResult.objects.create(
        study=study,
        status=StatusChoices.APPROVED,
        generated_report={
            "birads": "4C",
            "size": "12",
            "location": "KGZ",
        },
        accepted_report={
            "birads": "4C",
            "size": "12",
            "location": "KGZ",
        },
    )

    with mock.patch("review.views.OrthancClient") as orthanc:
        orthanc.return_value.list_studies.return_value = [
            {
                "orthanc_id": study.orthanc_path,
                "study_date": "20261026",
                "patient_id": "PATIENT-123",
                "description": "MRI breast",
                "study_instance_uid": "1.2.3.4",
            }
        ]

        response = authenticated_client.get(
            reverse(
                "review-overview",
                kwargs={"study_id": study.orthanc_path},
            )
        )

    assert response.status_code == status.HTTP_200_OK
    assert response.data["studyId"] == study.orthanc_path
    assert response.data["patientId"] == "PATIENT-123"
    assert response.data["studyDate"] == "2026-10-26"
    assert response.data["status"] == "verified"
    assert response.data["mask"]["corrected"] is False
    assert response.data["mask"]["by"] == "Jan Kowalski"
    assert response.data["verification"]["by"] == "Jan Kowalski"
    assert response.data["report"] is not None


@pytest.mark.django_db
def test_review_overview_marks_corrected_segmentation_as_saving_when_no_accepted_path(
    authenticated_client,
    study,
):
    SegmentationResult.objects.create(
        study=study,
        status=StatusChoices.CORRECTED,
        accepted_path=None,
    )

    with mock.patch("review.views.OrthancClient") as orthanc:
        orthanc.return_value.list_studies.return_value = []

        response = authenticated_client.get(
            reverse(
                "review-overview",
                kwargs={"study_id": study.orthanc_path},
            )
        )

    assert response.status_code == status.HTTP_200_OK
    assert response.data["status"] == "saving"
    assert response.data["mask"]["corrected"] is True


@pytest.mark.django_db
def test_review_overview_returns_404_for_unknown_study(
    authenticated_client,
):
    response = authenticated_client.get(
        reverse(
            "review-overview",
            kwargs={"study_id": "unknown-study"},
        )
    )

    assert response.status_code == status.HTTP_404_NOT_FOUND
