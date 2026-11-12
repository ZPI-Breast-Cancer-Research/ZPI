import pytest
from django.urls import reverse
from rest_framework import status

from extraction.models import ExtractionResult, StatusChoices
from mlops.models import ModelVersion


@pytest.mark.django_db
def test_extraction_overview_requires_authentication(api_client):
    response = api_client.get(
        reverse("extraction-overview")
    )

    assert response.status_code in [401, 403]


@pytest.mark.django_db
def test_extraction_overview_returns_200(authenticated_client):
    response = authenticated_client.get(
        reverse("extraction-overview")
    )

    assert response.status_code == status.HTTP_200_OK


@pytest.mark.django_db
def test_extraction_overview_empty_data(authenticated_client):
    response = authenticated_client.get(
        reverse("extraction-overview")
    )

    data = response.json()

    assert data["version"] is None
    assert data["since"] is None
    assert data["examplePool"] == 0
    assert isinstance(data["fields"], list)


@pytest.mark.django_db
def test_extraction_overview_returns_production_version(
    authenticated_client
):
    model = ModelVersion.objects.create(
        module="ext",
        name="extraction",
        version="ext-1",
        status=ModelVersion.StatusChoices.PRODUCTION
    )

    response = authenticated_client.get(
        reverse("extraction-overview")
    )

    data = response.json()

    assert data["version"] == model.version


@pytest.mark.django_db
def test_extraction_overview_counts_approved_reports(
    authenticated_client,
    study
):
    model = ModelVersion.objects.create(
        module="ext",
        name="extraction",
        version="ext-2",
        status=ModelVersion.StatusChoices.PRODUCTION
    )

    ExtractionResult.objects.create(
        study=study,
        model=model,
        status=StatusChoices.APPROVED,
        generated_report={"birads": "3"},
        accepted_report={"birads": "4"}
    )

    ExtractionResult.objects.create(
        study=study,
        model=model,
        status=StatusChoices.PENDING,
        accepted_report={"birads": "2"}
    )

    response = authenticated_client.get(
        reverse("extraction-overview")
    )

    data = response.json()

    assert data["examplePool"] == 1


@pytest.mark.django_db
def test_extraction_overview_calculates_field_corrections(
    authenticated_client,
    study
):
    model = ModelVersion.objects.create(
        module="ext",
        name="extraction",
        version="ext-3",
        status=ModelVersion.StatusChoices.PRODUCTION
    )

    ExtractionResult.objects.create(
        study=study,
        model=model,
        status=StatusChoices.APPROVED,
        generated_report={"birads": "3"},
        accepted_report={"birads": "4"}
    )

    response = authenticated_client.get(
        reverse("extraction-overview")
    )

    data = response.json()

    birads = next(
        field for field in data["fields"]
        if field["field"] == "BI-RADS"
    )

    assert birads["correctedShare"] == 1.0


@pytest.mark.django_db
def test_extraction_overview_returns_zero_when_field_unchanged(
    authenticated_client,
    study
):
    model = ModelVersion.objects.create(
        module="ext",
        name="extraction",
        version="ext-4",
        status=ModelVersion.StatusChoices.PRODUCTION
    )

    ExtractionResult.objects.create(
        study=study,
        model=model,
        status=StatusChoices.APPROVED,
        generated_report={"birads": "3"},
        accepted_report={"birads": "3"}
    )

    response = authenticated_client.get(
        reverse("extraction-overview")
    )

    data = response.json()

    birads = next(
        field for field in data["fields"]
        if field["field"] == "BI-RADS"
    )

    assert birads["correctedShare"] == 0.0
