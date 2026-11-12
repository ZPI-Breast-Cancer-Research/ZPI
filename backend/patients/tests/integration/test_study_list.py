from unittest import mock
import pytest
from django.urls import reverse

from patients.models import Study
from patients.views import OrthancUnavailable


@pytest.mark.django_db
@mock.patch("patients.views._orthanc_studies")
def test_study_list_returns_orthanc_studies(
    mock_orthanc,
    authenticated_client,
    study,
):
    mock_orthanc.return_value = [
        {
            "orthanc_id": study.orthanc_path,
            "study_instance_uid": "1.2.3.4.5",
            "patient_id": "P123",
            "study_date": "20250101",
            "description": "Test study",
            "modalities": ["CT"],
            "series_count": 1,
            "viewer_url": "http://orthanc/viewer",
        }
    ]

    response = authenticated_client.get(reverse("study-list"))

    assert response.status_code == 200
    assert len(response.data) >= 1


@pytest.mark.django_db
@mock.patch("patients.views._orthanc_studies", side_effect=OrthancUnavailable)
def test_study_list_returns_empty_list_when_orthanc_unavailable(
    mock_orthanc,
    authenticated_client,
):
    response = authenticated_client.get(reverse("study-list"))

    assert response.status_code == 503 


@pytest.mark.django_db
@mock.patch(
    "patients.views._orthanc_studies",
    return_value=[
        {
            "orthanc_id": "unknown-study",
            "MainDicomTags": {},
        }
    ],
)
def test_study_list_does_not_return_unknown_orthanc_study(
    mock_orthanc,
    authenticated_client,
):
    response = authenticated_client.get(reverse("study-list"))

    assert response.status_code == 200
    assert not any(
        item.get("orthanc_path") == "unknown-study"
        for item in response.data
    )