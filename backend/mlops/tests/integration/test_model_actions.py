from unittest import mock

import pytest
from django.urls import reverse
from rest_framework import status

from mlops.models import ModelVersion


@pytest.mark.django_db
def test_promote_model(
    authenticated_client,
    user,
    production_model,
    candidate_model
):
    response = authenticated_client.post(
        reverse(
            "promote-model",
            kwargs={"version": candidate_model.version}
        )
    )

    assert response.status_code == status.HTTP_200_OK
    assert response.json() == candidate_model.version

    production_model.refresh_from_db()
    candidate_model.refresh_from_db()

    assert production_model.status == ModelVersion.StatusChoices.ARCHIVED
    assert production_model.deactivated_at is not None

    assert candidate_model.status == ModelVersion.StatusChoices.PRODUCTION
    assert candidate_model.decision == ModelVersion.DecisionChoices.PROMOTED
    assert candidate_model.activated_at is not None
    assert candidate_model.decided_by == user


@pytest.mark.django_db
def test_reject_model(authenticated_client, user, candidate_model):
    response = authenticated_client.post(
        reverse(
            "reject-model",
            kwargs={"version": candidate_model.version}
        ),
        {"reason": "Bad model"},
        format="json"
    )

    assert response.status_code == status.HTTP_200_OK

    candidate_model.refresh_from_db()

    assert candidate_model.status == ModelVersion.StatusChoices.REJECTED
    assert candidate_model.decision == ModelVersion.DecisionChoices.REJECTED
    assert candidate_model.decided_by == user


@pytest.mark.django_db
def test_reject_model_without_reason(authenticated_client, candidate_model):
    response = authenticated_client.post(
        reverse(
            "reject-model",
            kwargs={"version": candidate_model.version}
        )
    )

    assert response.status_code == status.HTTP_200_OK

    candidate_model.refresh_from_db()

    assert candidate_model.status == ModelVersion.StatusChoices.REJECTED


@pytest.mark.django_db
def test_rollback_model(
    authenticated_client,
    user,
    production_model
):
    old_model = ModelVersion.objects.create(
        module="seg",
        name="segmentation",
        version="old-archived",
        status=ModelVersion.StatusChoices.ARCHIVED
    )

    response = authenticated_client.post(
        reverse(
            "rollback-model",
            kwargs={"version": old_model.version}
        )
    )

    assert response.status_code == status.HTTP_200_OK

    production_model.refresh_from_db()
    old_model.refresh_from_db()

    assert production_model.status == ModelVersion.StatusChoices.ARCHIVED
    assert production_model.deactivated_at is not None

    assert old_model.status == ModelVersion.StatusChoices.PRODUCTION
    assert old_model.decision == ModelVersion.DecisionChoices.PROMOTED
    assert old_model.activated_at is not None
    assert old_model.decided_by == user


@pytest.mark.django_db
def test_promote_nonexistent_model_returns_404(authenticated_client):
    response = authenticated_client.post(
        reverse(
            "promote-model",
            kwargs={"version": "does-not-exist"}
        )
    )

    assert response.status_code == status.HTTP_404_NOT_FOUND


@pytest.mark.django_db
def test_reject_nonexistent_model_returns_404(authenticated_client):
    response = authenticated_client.post(
        reverse(
            "reject-model",
            kwargs={"version": "does-not-exist"}
        )
    )

    assert response.status_code == status.HTTP_404_NOT_FOUND


@pytest.mark.django_db
def test_rollback_nonexistent_model_returns_404(authenticated_client):
    response = authenticated_client.post(
        reverse(
            "rollback-model",
            kwargs={"version": "does-not-exist"}
        )
    )

    assert response.status_code == status.HTTP_404_NOT_FOUND


@pytest.mark.django_db
def test_start_training_sends_celery_task(authenticated_client):
    from mlops import views

    with mock.patch.object(
        views.current_app,
        "send_task"
    ) as send_task:

        response = authenticated_client.post(
            reverse("start-training")
        )

    assert response.status_code == status.HTTP_200_OK

    send_task.assert_called_once_with(
        "training.run",
        kwargs={"training_run_id": 1}
    )
