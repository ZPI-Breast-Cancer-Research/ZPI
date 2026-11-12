import pytest
from django.urls import reverse

from extraction.models import ExtractionResult


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