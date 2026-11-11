# users/tests/test_auth.py

import pytest
from django.urls import reverse


@pytest.mark.django_db
def test_login_requires_login(api_client):
    response = api_client.post(
        reverse("sign-in"),
        {"password": "Password123!"},
        format="json",
    )

    assert response.status_code == 400
    assert response.data["detail"] == "Brak loginu lub hasła."


@pytest.mark.django_db
def test_login_requires_password(api_client):
    response = api_client.post(
        reverse("sign-in"),
        {"login": "radiologist"},
        format="json",
    )

    assert response.status_code == 400
    assert response.data["detail"] == "Brak loginu lub hasła."


@pytest.mark.django_db
def test_login_rejects_wrong_password(api_client, radiologist):
    response = api_client.post(
        reverse("sign-in"),
        {
            "login": radiologist.username,
            "password": "WrongPassword123!",
        },
        format="json",
    )

    assert response.status_code == 401
    assert response.data["detail"] == "bad credentials"


@pytest.mark.django_db
def test_login_rejects_unknown_user(api_client):
    response = api_client.post(
        reverse("sign-in"),
        {
            "login": "unknown",
            "password": "Password123!",
        },
        format="json",
    )

    assert response.status_code == 401


@pytest.mark.django_db
def test_login_returns_first_login_response(api_client, first_login_user):
    response = api_client.post(
        reverse("sign-in"),
        {
            "login": first_login_user.username,
            "password": "TemporaryPassword123!",
        },
        format="json",
    )

    assert response.status_code == 200
    assert response.data == {
        "kind": "first-login",
        "login": "firstlogin",
    }

    # Użytkownik nie powinien zostać zalogowany.
    assert "_auth_user_id" not in api_client.session


@pytest.mark.django_db
def test_login_successfully_authenticates_user(api_client, radiologist):
    response = api_client.post(
        reverse("sign-in"),
        {
            "login": radiologist.username,
            "password": "OldPassword123!",
        },
        format="json",
    )

    assert response.status_code == 200
    assert response.data["kind"] == "signed-in"

    assert response.data["user"] == {
        "login": "radiologist",
        "name": "Jan Kowalski",
        "role": "radiologist",
    }

    assert api_client.session["_auth_user_id"] == str(radiologist.pk)


@pytest.mark.django_db
def test_login_uses_username_when_name_is_empty(api_client, db):
    from django.contrib.auth import get_user_model

    User = get_user_model()

    User.objects.create_user(
        username="nameless",
        password="Password123!",
        first_name="",
        last_name="",
    )

    response = api_client.post(
        reverse("sign-in"),
        {
            "login": "nameless",
            "password": "Password123!",
        },
        format="json",
    )

    assert response.status_code == 200
    assert response.data["user"]["name"] == "nameless"


@pytest.mark.django_db
def test_set_first_password_requires_login(api_client):
    response = api_client.post(
        reverse("set-password"),
        {"password": "NewPassword123!"},
        format="json",
    )

    assert response.status_code == 400
    assert response.data["detail"] == "Wymagany login i nowe hasło."


@pytest.mark.django_db
def test_set_first_password_requires_new_password(api_client):
    response = api_client.post(
        reverse("set-password"),
        {"login": "firstlogin"},
        format="json",
    )

    assert response.status_code == 400


@pytest.mark.django_db
def test_set_first_password_returns_404_for_unknown_user(api_client):
    response = api_client.post(
        reverse("set-password"),
        {
            "login": "unknown",
            "password": "NewPassword123!",
        },
        format="json",
    )

    assert response.status_code == 404
    assert response.data["detail"] == "Użytkownik nie istnieje."


@pytest.mark.django_db
def test_set_first_password_changes_password(
    api_client,
    first_login_user,
):
    response = api_client.post(
        reverse("set-password"),
        {
            "login": first_login_user.username,
            "temporary": "TemporaryPassword123!",
            "password": "NewPassword123!",
        },
        format="json",
    )

    assert response.status_code == 200

    first_login_user.refresh_from_db()

    assert first_login_user.check_password("NewPassword123!")
    assert not first_login_user.is_first_login


@pytest.mark.django_db
def test_set_first_password_returns_user_data(
    api_client,
    first_login_user,
):
    response = api_client.post(
        reverse("set-password"),
        {
            "login": first_login_user.username,
            "password": "NewPassword123!",
        },
        format="json",
    )

    assert response.status_code == 200
    assert response.data == {
        "login": "firstlogin",
        "name": "Piotr Testowy",
        "role": "radiologist",
    }


@pytest.mark.django_db
def test_sign_out_returns_204(api_client, radiologist):
    api_client.force_login(radiologist)

    response = api_client.post(reverse("sign-out"))

    assert response.status_code == 204
    assert "_auth_user_id" not in api_client.session
