from unittest import mock
import pytest
from django.urls import reverse


@pytest.mark.django_db
def test_study_import_requires_authentication(api_client):
    response = api_client.post(
        reverse("study-import"),
        {},
        format="multipart",
    )

    assert response.status_code in (401, 403)


@pytest.mark.django_db
def test_study_import_forbidden_for_researcher(researcher_client):
    response = researcher_client.post(
        reverse("study-import"),
        {},
        format="multipart",
    )

    assert response.status_code == 403


@pytest.mark.django_db
@mock.patch("patients.views._check_archive", return_value=(False, "No archive"))
def test_study_import_allowed_for_radiologist(mock_check_archive, authenticated_client):
    response = authenticated_client.post(
        reverse("study-import"),
        {},
        format="multipart",
    )

    assert response.status_code != 403


@pytest.mark.django_db
def test_attach_report_requires_permission(researcher_client):
    response = researcher_client.post(
        "/api/studies/orthanc-study-123/attach-report/",
        {},
        format="multipart",
    )

    assert response.status_code == 403