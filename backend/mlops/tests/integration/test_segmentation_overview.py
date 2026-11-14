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
    assert candidate["metrics"]["dice"] == candidate_model.metrics["dice"]


@pytest.mark.django_db
def test_segmentation_overview_candidate_without_metrics(
    authenticated_client,
):
    candidate = ModelVersion.objects.create(
        module=ModelVersion.ModuleChoices.SEG,
        name="segmentation",
        version="no-metrics",
        status=ModelVersion.StatusChoices.CANDIDATE,
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
    production_model.periods.create(started_at=timezone.now())

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
    )
    previous.periods.create(started_at=timezone.now(), ended_at=timezone.now())

    response = authenticated_client.get(reverse("segmentation-overview"))

    data = response.json()

    assert data["compareWith"] == previous.version


@pytest.mark.django_db
def test_segmentation_overview_tells_a_proposed_version_from_a_new_one(authenticated_client):
    for version, state in (("draft", ModelVersion.StatusChoices.NEW), ("waiting", ModelVersion.StatusChoices.CANDIDATE)):
        ModelVersion.objects.create(module="seg", name="segmentation", version=version, status=state)

    data = authenticated_client.get(reverse("segmentation-overview")).json()

    statuses = {version["version"]: version["status"] for version in data["versions"]}
    assert statuses == {"draft": "new", "waiting": "proposed"}


@pytest.mark.django_db
def test_segmentation_overview_returns_every_usage_period_and_the_new_fields(
    authenticated_client,
    user,
):
    restored = ModelVersion.objects.create(
        module="seg",
        name="segmentation",
        version="restored",
        proposed_by=user,
        reason="Back to the stable one",
        trained_at=timezone.now(),
        training_cases=120,
        dataset="Dataset501_DCE3",
        metrics={"dice": 0.9, "iou": 0.82, "dice_small": 0.7, "volume_error_pct": 4.5},
        metrics_cases=30,
    )
    other = ModelVersion.objects.create(module="seg", name="segmentation", version="other")
    restored.put_in_use(user)
    other.put_in_use(user)
    restored.put_in_use(user, reason="Back to the stable one")

    data = authenticated_client.get(reverse("segmentation-overview")).json()

    version = next(v for v in data["versions"] if v["version"] == "restored")
    assert len(version["periods"]) == 2
    assert version["periods"][0]["to"] is not None
    assert version["periods"][1]["to"] is None
    assert version["trainingCases"] == 120
    assert version["trainedAt"] is not None
    assert version["proposedBy"]["login"] == user.username
    assert version["reason"] == "Back to the stable one"
    assert version["metrics"] == {
        "set": "Dataset501_DCE3",
        "cases": 30,
        "dice": 0.9,
        "iou": 0.82,
        "hd95": None,
        "diceSmall": 0.7,
        "volumeErrorPct": 4.5,
    }
    assert data["inUse"]["version"] == "restored"
    assert data["inUse"]["since"] is not None
    assert data["compareWith"] == "other"
