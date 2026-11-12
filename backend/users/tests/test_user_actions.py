# users/tests/test_user_actions.py

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse

User = get_user_model()


@pytest.mark.django_db
def test_update_user_changes_all_fields(admin_client, radiologist):
    response = admin_client.patch(
        reverse("update-user", kwargs={"user_id": radiologist.id}),
        {
            "name": "Tomasz Wiśniewski",
            "email": "tomasz@example.com",
            "role": "researcher",
            "pwz": "1112223",
        },
        format="json",
    )

    assert response.status_code == 204

    radiologist.refresh_from_db()

    assert radiologist.first_name == "Tomasz"
    assert radiologist.last_name == "Wiśniewski"
    assert radiologist.email == "tomasz@example.com"
    assert radiologist.role == "researcher"
    assert radiologist.pwz == "1112223"


@pytest.mark.django_db
def test_update_user_changes_only_name(admin_client, radiologist):
    response = admin_client.patch(
        reverse("update-user", kwargs={"user_id": radiologist.id}),
        {"name": "Piotr"},
        format="json",
    )

    assert response.status_code == 204

    radiologist.refresh_from_db()

    assert radiologist.first_name == "Piotr"
    assert radiologist.last_name == ""


@pytest.mark.django_db
def test_update_user_changes_only_email(admin_client, radiologist):
    response = admin_client.patch(
        reverse("update-user", kwargs={"user_id": radiologist.id}),
        {"email": "new@example.com"},
        format="json",
    )

    assert response.status_code == 204

    radiologist.refresh_from_db()

    assert radiologist.email == "new@example.com"
    assert radiologist.role == "radiologist"


@pytest.mark.django_db
def test_update_user_returns_404_for_unknown_user(admin_client):
    response = admin_client.patch(
        reverse("update-user", kwargs={"user_id": 999999}),
        {"name": "Unknown User"},
        format="json",
    )

    assert response.status_code == 404
    assert response.data["detail"] == "Użytkownik nie znaleziony."


@pytest.mark.django_db
def test_update_user_requires_admin(authenticated_client, radiologist):
    response = authenticated_client.patch(
        reverse("update-user", kwargs={"user_id": radiologist.id}),
        {"name": "New Name"},
        format="json",
    )

    assert response.status_code == 403


@pytest.mark.django_db
def test_set_blocked_blocks_user(admin_client, radiologist):
    response = admin_client.post(
        reverse("set-blocked", kwargs={"user_id": radiologist.id}),
        {"blocked": True},
        format="json",
    )

    assert response.status_code == 204

    radiologist.refresh_from_db()

    assert radiologist.is_active is False


@pytest.mark.django_db
def test_set_blocked_unblocks_user(admin_client, blocked_user):
    response = admin_client.post(
        reverse("set-blocked", kwargs={"user_id": blocked_user.id}),
        {"blocked": False},
        format="json",
    )

    assert response.status_code == 204

    blocked_user.refresh_from_db()

    assert blocked_user.is_active is True


@pytest.mark.django_db
def test_set_blocked_defaults_to_unblocked(admin_client, blocked_user):
    response = admin_client.post(
        reverse("set-blocked", kwargs={"user_id": blocked_user.id}),
        {},
        format="json",
    )

    assert response.status_code == 204

    blocked_user.refresh_from_db()

    # W widoku brak pola blocked oznacza False,
    # więc is_active zostaje ustawione na True.
    assert blocked_user.is_active is True


@pytest.mark.django_db
def test_set_blocked_returns_404_for_unknown_user(admin_client):
    response = admin_client.post(
        reverse("set-blocked", kwargs={"user_id": 999999}),
        {"blocked": True},
        format="json",
    )

    assert response.status_code == 404
    assert response.data["detail"] == "Użytkownik nie znaleziony."


@pytest.mark.django_db
def test_set_blocked_requires_admin(authenticated_client, radiologist):
    response = authenticated_client.post(
        reverse("set-blocked", kwargs={"user_id": radiologist.id}),
        {"blocked": True},
        format="json",
    )

    assert response.status_code == 403


@pytest.mark.django_db
def test_reset_password_changes_password_and_marks_first_login(
    admin_client,
    radiologist,
):
    response = admin_client.post(
        reverse("reset-password", kwargs={"user_id": radiologist.id}),
        {},
        format="json",
    )

    assert response.status_code == 200
    assert "password" in response.data

    temporary_password = response.data["password"]

    radiologist.refresh_from_db()

    assert radiologist.check_password(temporary_password)
    assert radiologist.is_first_login is True
    assert radiologist.is_active is True


@pytest.mark.django_db
def test_reset_password_unblocks_user(admin_client, blocked_user):
    response = admin_client.post(
        reverse("reset-password", kwargs={"user_id": blocked_user.id}),
        {},
        format="json",
    )

    assert response.status_code == 200

    blocked_user.refresh_from_db()

    assert blocked_user.is_active is True
    assert blocked_user.is_first_login is True


@pytest.mark.django_db
def test_reset_password_returns_404_for_unknown_user(admin_client):
    response = admin_client.post(
        reverse("reset-password", kwargs={"user_id": 999999}),
        {},
        format="json",
    )

    assert response.status_code == 404
    assert response.data["detail"] == "Użytkownik nie znaleziony."


@pytest.mark.django_db
def test_reset_password_requires_admin(authenticated_client, radiologist):
    response = authenticated_client.post(
        reverse("reset-password", kwargs={"user_id": radiologist.id}),
        {},
        format="json",
    )

    assert response.status_code == 403
