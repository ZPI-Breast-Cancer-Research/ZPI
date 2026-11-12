import pytest
from django.urls import reverse
from django.utils import timezone
from rest_framework import status

from mlops.models import ModelVersion
from segmentation.models import SegmentationResult, StatusChoices


@pytest.mark.django_db
def test_segmentation_overview_requires_authentication(api_client):
    response = api_client.get(reverse("segmentation-overview"))

    assert response.status_code in [401, 403]


@pytest.mark.django_db
def test_segmentation_overview_returns_200(authenticated_client):
    response = authenticated_client.get(reverse("segmentation-overview"))

    assert response.status_code == status.HTTP_200_OK


@pytest.mark.django_db
def test_segmentation_overview_empty_data(authenticated_client):
    response = authenticated_client.get(reverse("segmentation-overview"))

    data = response.json()

    assert data["inUse"] is None
    assert data["compareWith"] is None
    assert data["proposal"] is None
    assert data["versions"] == []

    assert data["training"]["corrections"] == 0
    assert data["training"]["run"] is None
    assert data["training"]["canStart"] is False
    assert "threshold" in data["training"]
    assert "window" in data["training"]


@pytest.mark.django_db
def test_segmentation_overview_returns_production_model(
    authenticated_client,
    production_model,
):
    response = authenticated_client.get(reverse("segmentation-overview"))

    data = response.json()

    assert data["inUse"]["version"] == production_model.version
    assert data["inUse"]["studies"] == 0
    assert data["inUse"]["rejected"] == []
    assert data["inUse"]["weakest"] is None

    assert any(
        version["version"] == production_model.version
        and version["status"] == "in_use"
        for version in data["versions"]
    )


@pytest.mark.django_db
def test_segmentation_overview_returns_candidate_model(
    authenticated_client,
    candidate_model,
):
    response = authenticated_client.get(reverse("segmentation-overview"))

    data = response.json()

    candidate = next(
        version
        for version in data["versions"]
        if version["version"] == candidate_model.version
    )

    assert candidate["status"] in ["proposed", "new"]


@pytest.mark.django_db
def test_segmentation_overview_returns_candidate_metrics(
    authenticated_client,
    candidate_model,
):
    response = authenticated_client.get(reverse("segmentation-overview"))

    data = response.json()

    candidate = next(
        version
        for version in data["versions"]
        if version["version"] == candidate_model.version
    )

    assert candidate["metrics"] is not None
    assert candidate["metrics"]["dice"] == candidate_model.dice


@pytest.mark.django_db
def test_segmentation_overview_candidate_without_metrics(
    authenticated_client,
):
    candidate = ModelVersion.objects.create(
        module=ModelVersion.ModuleChoices.SEG,
        name="segmentation",
        version="no-metrics",
        status=ModelVersion.StatusChoices.CANDIDATE,
        dice=None,
        hd95=None,
    )

    response = authenticated_client.get(reverse("segmentation-overview"))

    data = response.json()

    version = next(
        version
        for version in data["versions"]
        if version["version"] == candidate.version
    )

    assert version["metrics"] is None


@pytest.mark.django_db
def test_segmentation_overview_calculates_agreement(
    authenticated_client,
    production_model,
    study,
):
    # agreement jest zwracane tylko dla wersji, która była aktywowana.
    production_model.activated_at = timezone.now()
    production_model.save(update_fields=["activated_at"])

    SegmentationResult.objects.create(
        study=study,
        model=production_model,
        status=StatusChoices.APPROVED,
    )

    SegmentationResult.objects.create(
        study=study,
        model=production_model,
        status=StatusChoices.CORRECTED,
    )

    response = authenticated_client.get(reverse("segmentation-overview"))

    data = response.json()

    production = next(
        version
        for version in data["versions"]
        if version["version"] == production_model.version
    )

    # Jedna z dwóch zaakceptowanych segmentacji została poprawiona.
    # Backend zwraca udział niezmienionych segmentacji.
    assert production["agreement"]["approved"] == 2
    assert production["agreement"]["unchanged"] == 0.5


@pytest.mark.django_db
def test_segmentation_overview_returns_training_model(
    authenticated_client,
):
    training_model = ModelVersion.objects.create(
        module=ModelVersion.ModuleChoices.SEG,
        name="segmentation",
        version="training-1",
        status=ModelVersion.StatusChoices.TRAINING,
    )

    response = authenticated_client.get(reverse("segmentation-overview"))

    data = response.json()

    assert data["training"]["run"]["version"] == training_model.version
    assert data["training"]["run"]["canStop"] is False
    assert data["training"]["run"]["epoch"] is None
    assert data["training"]["run"]["epochs"] is None
    assert data["training"]["run"]["etaHours"] is None


@pytest.mark.django_db
def test_segmentation_overview_returns_rejected_model(
    authenticated_client,
):
    model = ModelVersion.objects.create(
        module=ModelVersion.ModuleChoices.SEG,
        name="segmentation",
        version="rejected-1",
        status=ModelVersion.StatusChoices.REJECTED,
    )

    response = authenticated_client.get(reverse("segmentation-overview"))

    data = response.json()

    rejected = next(
        version
        for version in data["versions"]
        if version["version"] == model.version
    )

    assert rejected["status"] == "rejected"


@pytest.mark.django_db
def test_segmentation_overview_returns_previous_model(
    authenticated_client,
    production_model,
):
    previous = ModelVersion.objects.create(
        module=ModelVersion.ModuleChoices.SEG,
        name="segmentation",
        version="previous-1",
        status=ModelVersion.StatusChoices.ARCHIVED,
        activated_at=timezone.now(),
        deactivated_at=timezone.now(),
    )

    response = authenticated_client.get(reverse("segmentation-overview"))

    data = response.json()

    assert data["compareWith"] == previous.version