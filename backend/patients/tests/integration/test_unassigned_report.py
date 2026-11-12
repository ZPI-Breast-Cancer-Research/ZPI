import pytest
from django.urls import reverse

from extraction.models import ExtractionResult, StatusChoices


@pytest.mark.django_db
def test_unassigned_reports_returns_unassigned_reports(
    authenticated_client,
    unassigned_extraction_result,
):
    response = authenticated_client.get(
        reverse("unassigned-reports-list")
    )

    assert response.status_code == 200

    ids = [
        item.get("id")
        for item in response.data
    ]

    assert str(unassigned_extraction_result.id) in ids


@pytest.mark.django_db
def test_unassigned_reports_does_not_return_assigned_reports(
    authenticated_client,
    extraction_result,
):
    response = authenticated_client.get(
        reverse("unassigned-reports-list")
    )

    assert response.status_code == 200

    ids = [
        item.get("id")
        for item in response.data
    ]

    assert str(extraction_result.id) not in ids


@pytest.mark.django_db
def test_unassigned_reports_returns_empty_list_when_none_exist(
    authenticated_client,
):
    response = authenticated_client.get(
        reverse("unassigned-reports-list")
    )

    assert response.status_code == 200
    assert response.data == []


@pytest.mark.django_db
def test_unassigned_reports_show_a_failed_extraction(authenticated_client):
    # Arrange
    failed = ExtractionResult.objects.create(
        report_path="reports/abc/opis.txt", status=StatusChoices.FAILED, error="LLM: down"
    )

    # Act
    response = authenticated_client.get(reverse("unassigned-reports-list"))

    # Assert
    item = next(item for item in response.data if item["id"] == str(failed.id))
    assert item["status"] == "FAILED"
    assert item["error"] == "LLM: down"
    assert item["addedAt"] is not None


@pytest.mark.django_db
def test_unassigned_reports_hide_a_stale_error_of_a_retried_extraction(authenticated_client):
    # Arrange
    ExtractionResult.objects.create(
        report_path="reports/abc/opis.txt", status=StatusChoices.COMPLETED, error="old"
    )

    # Act
    response = authenticated_client.get(reverse("unassigned-reports-list"))

    # Assert
    assert response.data[0]["status"] == "COMPLETED"
    assert response.data[0]["error"] == ""
