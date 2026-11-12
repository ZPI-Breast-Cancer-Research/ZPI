# users/tests/test_profile.py

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse

User = get_user_model()


@pytest.mark.django_db
def test_get_profile_returns_user_data(
    authenticated_client,
):
    response = authenticated_client.get(reverse("get-profile"))

    assert response.status_code == 200

    assert response.data == {
        "name": "Jan Kowalski",
        "login": "radiologist",
        "email": "jan@example.com",
        "role": "radiologist",
        "pwz": "1234567",
    }


@pytest.mark.django_db
def test_get_profile_requires_authentication(api_client):
    response = api_client.get(reverse("get-profile"))

    assert response.status_code in (401, 403)


@pytest.mark.django_db
def test_get_profile_uses_username_when_name_is_empty(api_client):
    user = User.objects.create_user(
        username="nameless",
        password="Password123!",
        first_name="",
        last_name="",
    )

    api_client.force_authenticate(user=user)

    response = api_client.get(reverse("get-profile"))

    assert response.status_code == 200
    assert response.data["name"] == "nameless"


@pytest.mark.django_db
def test_get_profile_uses_generated_email_when_email_is_empty(api_client):
    user = User.objects.create_user(
        username="noemail",
        password="Password123!",
        email="",
    )

    api_client.force_authenticate(user=user)

    response = api_client.get(reverse("get-profile"))

    assert response.status_code == 200
    assert response.data["email"] == "noemail@szpital.pl"


@pytest.mark.django_db
def test_get_profile_returns_pwz_none_when_not_set(api_client):
    user = User.objects.create_user(
        username="withoutpwz",
        password="Password123!",
    )

    api_client.force_authenticate(user=user)

    response = api_client.get(reverse("get-profile"))

    assert response.status_code == 200
    assert response.data["pwz"] is None
