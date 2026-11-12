import pytest
from unittest import mock
from django.urls import reverse
from rest_framework import status

from segmentation.models import SegmentationResult
from extraction.models import StatusChoices


@pytest.mark.django_db
def test_review_case_detail_by_orthanc_id(
    authenticated_client,
    study,
    segmentation,
    extraction,
):
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
                "review-case-detail",
                kwargs={"study_id": study.orthanc_path},
            )
        )

    assert response.status_code == status.HTTP_200_OK
    assert response.data["studyId"] == study.orthanc_path
    assert response.data["patientId"] == "PATIENT-123"
    assert response.data["studyDate"] == "2026-10-26"
    assert response.data["description"] == "MRI breast"
    assert response.data["studyUid"] == "1.2.3.4"
    assert response.data["uncertainty"] == 0.75
    assert response.data["proposals"] == {
        "birads": {"value": "4C"},
        "size": {"value": "12"},
        "location": {"value": "KGZ"},
    }


@pytest.mark.django_db
def test_review_case_detail_by_database_id(
    authenticated_client,
    study,
):
    response = authenticated_client.get(
        reverse(
            "review-case-detail",
            kwargs={"study_id": str(study.id)},
        )
    )

    assert response.status_code == status.HTTP_200_OK
    assert response.data["studyId"] == study.orthanc_path


@pytest.mark.django_db
def test_review_case_detail_returns_404_for_unknown_orthanc_id(
    authenticated_client,
):
    response = authenticated_client.get(
        reverse(
            "review-case-detail",
            kwargs={"study_id": "unknown-study"},
        )
    )

    assert response.status_code == status.HTTP_404_NOT_FOUND


@pytest.mark.django_db
def test_review_case_detail_uses_default_values_without_results(
    authenticated_client,
    study,
):
    with mock.patch("review.views.OrthancClient") as orthanc:
        orthanc.return_value.list_studies.return_value = []

        response = authenticated_client.get(
            reverse(
                "review-case-detail",
                kwargs={"study_id": study.orthanc_path},
            )
        )

    assert response.status_code == status.HTTP_200_OK
    assert response.data["uncertainty"] == 0.5
    assert response.data["patientId"] == "---"
    assert response.data["description"] == "MR piersi z kontrastem"
    assert response.data["segmentationVersion"] == "-"
    assert response.data["extractionVersion"] is None
    assert response.data["proposals"] == {}


@pytest.mark.django_db
def test_review_case_detail_returns_corrected_mask_status(
    authenticated_client,
    study,
    reviewer,
):
    SegmentationResult.objects.create(
        study=study,
        status=StatusChoices.CORRECTED,
        accepted_by=reviewer,
    )

    response = authenticated_client.get(
        reverse(
            "review-case-detail",
            kwargs={"study_id": study.orthanc_path},
        )
    )

    assert response.status_code == status.HTTP_200_OK
    assert response.data["maskApproved"] == "corrected"


@pytest.mark.django_db
def test_review_case_detail_returns_confirmed_mask_status(
    authenticated_client,
    study,
):
    SegmentationResult.objects.create(
        study=study,
        status=StatusChoices.APPROVED,
    )

    response = authenticated_client.get(
        reverse(
            "review-case-detail",
            kwargs={"study_id": study.orthanc_path},
        )
    )

    assert response.status_code == status.HTTP_200_OK
    assert response.data["maskApproved"] == "confirmed"
