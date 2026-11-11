# users/tests/test_passwords.py

import pytest
from django.urls import reverse

from users.views import generate_temporary_password


@pytest.mark.django_db
def test_change_password_successfully(authenticated_client, radiologist):
    response = authenticated_client.post(
        reverse("change-password"),
        {
            "current": "OldPassword123!",
            "next": "NewPassword123!",
        },
        format="json",
    )

    assert response.status_code == 204

    radiologist.refresh_from_db()

    assert radiologist.check_password("NewPassword123!")
    assert not radiologist.is_first_login


@pytest.mark.django_db
def test_change_password_rejects_wrong_current_password(
    authenticated_client,
    radiologist,
):
    response = authenticated_client.post(
        reverse("change-password"),
        {
            "current": "WrongPassword123!",
            "next": "NewPassword123!",
        },
        format="json",
    )

    assert response.status_code == 400
    assert response.data["detail"] == "Stare hasło jest niepoprawne."

    radiologist.refresh_from_db()

    assert radiologist.check_password("OldPassword123!")


@pytest.mark.django_db
def test_change_password_requires_authentication(api_client):
    response = api_client.post(
        reverse("change-password"),
        {
            "current": "OldPassword123!",
            "next": "NewPassword123!",
        },
        format="json",
    )

    assert response.status_code in (401, 403)


@pytest.mark.django_db
def test_change_password_clears_first_login_flag(
    api_client,
    first_login_user,
):
    api_client.force_authenticate(user=first_login_user)

    response = api_client.post(
        reverse("change-password"),
        {
            "current": "TemporaryPassword123!",
            "next": "NewPassword123!",
        },
        format="json",
    )

    assert response.status_code == 204

    first_login_user.refresh_from_db()

    assert first_login_user.is_first_login is False


def test_generate_temporary_password_has_default_length():
    password = generate_temporary_password()

    assert len(password) == 14


def test_generate_temporary_password_uses_only_allowed_characters():
    password = generate_temporary_password()

    allowed_characters = (
        "abcdefghjkmnpqrstuvwxyz"
        "ABCDEFGHJKLMNPQRSTUVWXYZ"
        "23456789"
    )

    assert all(character in allowed_characters for character in password)


@pytest.mark.parametrize("length", [1, 8, 14, 20, 32])
def test_generate_temporary_password_respects_requested_length(length):
    password = generate_temporary_password(length)

    assert len(password) == length


def test_generate_temporary_password_returns_string():
    password = generate_temporary_password()

    assert isinstance(password, str)


def test_generate_temporary_password_generates_different_values():
    passwords = {
        generate_temporary_password()
        for _ in range(30)
    }

    assert len(passwords) > 1
