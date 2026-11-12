from unittest import mock
import pytest
from django.urls import reverse

from patients.models import Study
from extraction.models import ExtractionResult
from segmentation.models import SegmentationResult
from patients.views import OrthancUnavailable


@pytest.mark.django_db
@mock.patch("patients.views._orthanc_studies", return_value=[])
def test_dashboard_returns_200(mock_orthanc, authenticated_client):
    response = authenticated_client.get(
        reverse("dashboard-view")
    )

    assert response.status_code == 200
    assert isinstance(response.data, dict)


@pytest.mark.django_db
@mock.patch("patients.views._orthanc_studies")
def test_dashboard_counts_studies(mock_orthanc, authenticated_client, study):
    mock_orthanc.return_value = [
        {
            "ID": study.orthanc_path,
            "MainDicomTags": {},
        }
    ]

    response = authenticated_client.get(
        reverse("dashboard-view")
    )

    assert response.status_code == 200


@pytest.mark.django_db
@mock.patch("patients.views._orthanc_studies", side_effect=OrthancUnavailable)
def test_dashboard_handles_orthanc_unavailable(mock_orthanc, authenticated_client):
    response = authenticated_client.get(
        reverse("dashboard-view")
    )

    assert response.status_code == 200


@pytest.mark.django_db
@mock.patch("patients.views._orthanc_studies")
def test_dashboard_handles_study_without_extraction(mock_orthanc, authenticated_client, study):
    mock_orthanc.return_value = [
        {
            "ID": study.orthanc_path,
            "MainDicomTags": {},
        }
    ]

    response = authenticated_client.get(
        reverse("dashboard-view")
    )

    assert response.status_code == 200


@pytest.mark.django_db
@mock.patch("patients.views._orthanc_studies")
def test_dashboard_handles_study_with_completed_extraction(
    mock_orthanc,
    authenticated_client,
    study,
    extraction_result,
):
    mock_orthanc.return_value = [
        {
            "ID": study.orthanc_path,
            "MainDicomTags": {},
        }
    ]

    response = authenticated_client.get(
        reverse("dashboard-view")
    )

    assert response.status_code == 200