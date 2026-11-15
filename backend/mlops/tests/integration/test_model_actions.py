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

    assert candidate_model.status == ModelVersion.StatusChoices.PRODUCTION
    assert candidate_model.periods.get().ended_at is None
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
    assert candidate_model.reason == "Bad model"
    assert candidate_model.decided_by == user
    assert candidate_model.periods.count() == 0


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

    assert old_model.status == ModelVersion.StatusChoices.PRODUCTION
    assert old_model.periods.get().ended_at is None
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


@pytest.mark.django_db
@pytest.mark.parametrize(
    "action, before",
    [
        ("promote-model", ModelVersion.StatusChoices.CANDIDATE),
        ("reject-model", ModelVersion.StatusChoices.CANDIDATE),
        ("rollback-model", ModelVersion.StatusChoices.ARCHIVED),
    ],
)
def test_model_action_ignores_extraction_version_with_the_same_number(
    authenticated_client,
    action,
    before,
):
    segmentation = ModelVersion.objects.create(module="seg", name="segmentation", version="2.0", status=before)
    extraction = ModelVersion.objects.create(module="ext", name="extraction", version="2.0", status=before)

    response = authenticated_client.post(reverse(action, kwargs={"version": "2.0"}))

    assert response.status_code == status.HTTP_200_OK

    extraction.refresh_from_db()
    segmentation.refresh_from_db()

    assert extraction.status == before
    assert segmentation.status != before


@pytest.mark.django_db
def test_model_action_returns_404_for_a_version_only_extraction_has(authenticated_client):
    ModelVersion.objects.create(
        module=ModelVersion.ModuleChoices.EXT,
        name="extraction",
        version="ext-only",
    )

    response = authenticated_client.post(
        reverse("promote-model", kwargs={"version": "ext-only"})
    )

    assert response.status_code == status.HTTP_404_NOT_FOUND


@pytest.mark.django_db
@pytest.mark.parametrize("action", ["promote-model", "reject-model", "rollback-model"])
@pytest.mark.parametrize("role", ["researcher", "radiologist"])
def test_only_admin_decides_about_a_model(client_as, candidate_model, action, role):
    response = client_as(role).post(
        reverse(action, kwargs={"version": candidate_model.version})
    )

    assert response.status_code == status.HTTP_403_FORBIDDEN

    candidate_model.refresh_from_db()

    assert candidate_model.status == ModelVersion.StatusChoices.CANDIDATE


@pytest.mark.django_db
@pytest.mark.parametrize(
    "role, expected",
    [
        ("admin", status.HTTP_200_OK),
        ("researcher", status.HTTP_200_OK),
        ("radiologist", status.HTTP_403_FORBIDDEN),
    ],
)
def test_training_is_started_by_roles_that_propose_models(client_as, role, expected):
    from mlops import views

    with mock.patch.object(views.current_app, "send_task") as send_task:
        response = client_as(role).post(reverse("start-training"))

    assert response.status_code == expected
    assert send_task.called == (expected == status.HTTP_200_OK)


@pytest.mark.django_db
def test_promote_closes_the_period_of_the_replaced_version_and_saves_the_reason(
    authenticated_client,
    user,
    production_model,
    candidate_model,
):
    production_model.put_in_use(user)

    response = authenticated_client.post(
        reverse("promote-model", kwargs={"version": candidate_model.version}),
        {"reason": "Better on small lesions"},
        format="json",
    )

    assert response.status_code == status.HTTP_200_OK

    candidate_model.refresh_from_db()

    assert candidate_model.reason == "Better on small lesions"
    assert production_model.periods.get().ended_at is not None
    assert candidate_model.periods.get().ended_at is None


ALL = set(ModelVersion.StatusChoices.values)
ALLOWED = {
    "promote-model": {"new", "candidate"},
    "reject-model": {"new", "candidate"},
    "rollback-model": {"archived"},
}
REFUSED = [(action, state) for action, allowed in ALLOWED.items() for state in sorted(ALL - allowed)]


@pytest.mark.django_db
@pytest.mark.parametrize("action, state", REFUSED)
def test_model_action_is_refused_in_a_status_it_does_not_apply_to(
    authenticated_client,
    action,
    state,
):
    model = ModelVersion.objects.create(module="seg", name="segmentation", version="1", status=state)

    response = authenticated_client.post(reverse(action, kwargs={"version": "1"}))

    assert response.status_code == status.HTTP_409_CONFLICT
    assert response.json()["code"] == "wrong_status"

    model.refresh_from_db()

    assert model.status == state
    assert model.periods.count() == 0


@pytest.mark.django_db
def test_version_in_use_cannot_be_rejected_and_keeps_its_period(authenticated_client, user):
    model = ModelVersion.objects.create(module="seg", name="segmentation", version="1")
    model.put_in_use(user)

    response = authenticated_client.post(reverse("reject-model", kwargs={"version": "1"}))

    assert response.status_code == status.HTTP_409_CONFLICT

    model.refresh_from_db()

    assert model.status == ModelVersion.StatusChoices.PRODUCTION
    assert model.periods.get().ended_at is None


@pytest.mark.django_db
@pytest.mark.parametrize("state", ["new", "candidate"])
def test_draft_and_proposal_can_be_promoted_and_rejected(authenticated_client, state):
    for version, action in (("a", "promote-model"), ("b", "reject-model")):
        ModelVersion.objects.create(module="seg", name="segmentation", version=version, status=state)

        response = authenticated_client.post(reverse(action, kwargs={"version": version}))

        assert response.status_code == status.HTTP_200_OK
