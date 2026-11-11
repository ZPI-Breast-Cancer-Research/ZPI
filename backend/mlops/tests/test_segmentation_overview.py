import pytest
from django.urls import reverse
from rest_framework import status

from mlops.models import ModelVersion
from segmentation.models import SegmentationResult, StatusChoices


@pytest.mark.django_db
def test_segmentation_overview_requires_authentication(api_client):
    response = api_client.get(
        reverse("segmentation-overview")
    )

    assert response.status_code in [401, 403]


@pytest.mark.django_db
def test_segmentation_overview_returns_200(authenticated_client):
    response = authenticated_client.get(
        reverse("segmentation-overview")
    )

    assert response.status_code == status.HTTP_200_OK


@pytest.mark.django_db
def test_segmentation_overview_empty_data(authenticated_client):
    response = authenticated_client.get(
        reverse("segmentation-overview")
    )

    data = response.json()

    assert data["production"]["version"] == "-----"
    assert data["previous"] is None
    assert data["correctedShare"]["current"] is None
    assert data["correctedShare"]["previous"] is None
    assert data["candidate"] is None
    assert data["training"] is None
    assert data["versions"] == []


@pytest.mark.django_db
def test_segmentation_overview_returns_production_model(
    authenticated_client,
    production_model
):
    response = authenticated_client.get(
        reverse("segmentation-overview")
    )

    data = response.json()

    assert data["production"]["version"] == production_model.version


@pytest.mark.django_db
def test_segmentation_overview_returns_candidate_model(
    authenticated_client,
    candidate_model
):
    response = authenticated_client.get(
        reverse("segmentation-overview")
    )

    data = response.json()

    assert data["candidate"]["version"] == candidate_model.version


@pytest.mark.django_db
def test_candidate_gate_passes_when_dice_is_better(
    authenticated_client,
    production_model,
    candidate_model
):
    response = authenticated_client.get(
        reverse("segmentation-overview")
    )

    data = response.json()

    assert data["candidate"]["gate"][0]["passed"] is True


@pytest.mark.django_db
def test_candidate_gate_fails_when_dice_is_worse(
    authenticated_client,
    production_model
):
    ModelVersion.objects.create(
        module="seg",
        name="segmentation",
        version="worse-candidate",
        status=ModelVersion.StatusChoices.CANDIDATE,
        dice=0.70
    )

    response = authenticated_client.get(
        reverse("segmentation-overview")
    )

    data = response.json()

    assert data["candidate"]["gate"][0]["passed"] is False


@pytest.mark.django_db
def test_candidate_gate_is_none_when_dice_missing(
    authenticated_client,
    production_model
):
    ModelVersion.objects.create(
        module="seg",
        name="segmentation",
        version="no-dice",
        status=ModelVersion.StatusChoices.CANDIDATE,
        dice=None
    )

    response = authenticated_client.get(
        reverse("segmentation-overview")
    )

    data = response.json()

    assert data["candidate"]["gate"][0]["passed"] is None


@pytest.mark.django_db
def test_segmentation_overview_calculates_corrected_share(
    authenticated_client,
    production_model,
    study
):
    SegmentationResult.objects.create(
        study=study,
        model=production_model,
        status=StatusChoices.APPROVED
    )

    SegmentationResult.objects.create(
        study=study,
        model=production_model,
        status=StatusChoices.CORRECTED
    )

    response = authenticated_client.get(
        reverse("segmentation-overview")
    )

    data = response.json()

    assert data["correctedShare"]["current"] == 0.5


@pytest.mark.django_db
def test_segmentation_overview_returns_training_model(
    authenticated_client
):
    ModelVersion.objects.create(
        module="seg",
        name="segmentation",
        version="training-1",
        status=ModelVersion.StatusChoices.TRAINING
    )

    response = authenticated_client.get(
        reverse("segmentation-overview")
    )

    data = response.json()

    assert data["training"]["version"] == "training-1"
    assert data["next"] is None


@pytest.mark.django_db
def test_segmentation_overview_returns_rejected_model(
    authenticated_client
):
    model = ModelVersion.objects.create(
        module="seg",
        name="segmentation",
        version="rejected-1",
        status=ModelVersion.StatusChoices.REJECTED
    )

    response = authenticated_client.get(
        reverse("segmentation-overview")
    )

    data = response.json()

    assert data["lastRun"]["version"] == model.version
    assert data["lastRun"]["outcome"] == "rejected_gate"
