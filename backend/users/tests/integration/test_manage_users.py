# users/tests/test_manage_users.py

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse

User = get_user_model()


@pytest.mark.django_db
def test_manage_users_requires_authentication(api_client):
    response = api_client.get(reverse("manage-users"))

    assert response.status_code in (401, 403)


@pytest.mark.django_db
def test_manage_users_forbidden_for_radiologist(authenticated_client):
    response = authenticated_client.get(reverse("manage-users"))

    assert response.status_code == 403


@pytest.mark.django_db
def test_manage_users_forbidden_for_researcher(researcher_client):
    response = researcher_client.get(reverse("manage-users"))

    assert response.status_code == 403


@pytest.mark.django_db
def test_manage_users_allowed_for_admin(admin_client, radiologist):
    response = admin_client.get(reverse("manage-users"))

    assert response.status_code == 200
    assert isinstance(response.data, list)

    usernames = [item["login"] for item in response.data]

    assert "radiologist" in usernames


@pytest.mark.django_db
def test_manage_users_returns_active_state(admin_client, radiologist):
    response = admin_client.get(reverse("manage-users"))

    user_data = next(
        item for item in response.data
        if item["login"] == radiologist.username
    )

    assert user_data["state"] == "active"


@pytest.mark.django_db
def test_manage_users_returns_blocked_state(admin_client, blocked_user):
    response = admin_client.get(reverse("manage-users"))

    user_data = next(
        item for item in response.data
        if item["login"] == blocked_user.username
    )

    assert user_data["state"] == "blocked"


@pytest.mark.django_db
def test_manage_users_returns_temporary_state(
    admin_client,
    first_login_user,
):
    response = admin_client.get(reverse("manage-users"))

    user_data = next(
        item for item in response.data
        if item["login"] == first_login_user.username
    )

    assert user_data["state"] == "temporary"


@pytest.mark.django_db
def test_manage_users_uses_default_email(admin_client, db):
    user = User.objects.create_user(
        username="noemail",
        password="Password123!",
        email="",
    )

    response = admin_client.get(reverse("manage-users"))

    user_data = next(
        item for item in response.data
        if item["login"] == user.username
    )

    assert user_data["email"] == "noemail@szpital.pl"


@pytest.mark.django_db
def test_create_user_successfully(admin_client):
    response = admin_client.post(
        reverse("manage-users"),
        {
            "login": "newuser",
            "name": "Marek Nowak",
            "email": "marek@example.com",
            "role": "radiologist",
            "pwz": "7654321",
        },
        format="json",
    )

    assert response.status_code == 201
    assert "password" in response.data

    user = User.objects.get(username="newuser")

    assert user.first_name == "Marek"
    assert user.last_name == "Nowak"
    assert user.email == "marek@example.com"
    assert user.role == "radiologist"
    assert user.pwz == "7654321"
    assert user.is_first_login is True
    assert user.check_password(response.data["password"])


@pytest.mark.django_db
def test_create_user_uses_default_values(admin_client):
    response = admin_client.post(
        reverse("manage-users"),
        {
            "login": "defaultuser",
            "name": "Jan",
        },
        format="json",
    )

    assert response.status_code == 201

    user = User.objects.get(username="defaultuser")

    assert user.email == "defaultuser@szpital.pl"
    assert user.role == "radiologist"
    assert user.pwz is None
    assert user.first_name == "Jan"
    assert user.last_name == ""
    assert user.is_first_login is True


@pytest.mark.django_db
def test_create_user_with_existing_login_returns_400(
    admin_client,
    radiologist,
):
    response = admin_client.post(
        reverse("manage-users"),
        {
            "login": radiologist.username,
            "name": "Duplicate User",
        },
        format="json",
    )

    assert response.status_code == 400
    assert response.data["detail"] == "login-taken"


@pytest.mark.django_db
def test_create_user_forbidden_for_non_admin(authenticated_client):
    response = authenticated_client.post(
        reverse("manage-users"),
        {
            "login": "newuser",
            "name": "New User",
        },
        format="json",
    )

    assert response.status_code == 403
