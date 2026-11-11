# users/tests/conftest.py

import pytest
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient

User = get_user_model()


@pytest.fixture
def api_client():
    return APIClient()


@pytest.fixture
def radiologist(db):
    return User.objects.create_user(
        username="radiologist",
        password="OldPassword123!",
        first_name="Jan",
        last_name="Kowalski",
        email="jan@example.com",
        role="radiologist",
        pwz="1234567",
    )


@pytest.fixture
def researcher(db):
    return User.objects.create_user(
        username="researcher",
        password="OldPassword123!",
        first_name="Anna",
        last_name="Nowak",
        email="anna@example.com",
        role="researcher",
    )


@pytest.fixture
def admin_user(db):
    return User.objects.create_user(
        username="admin",
        password="AdminPassword123!",
        first_name="Adam",
        last_name="Admin",
        email="admin@example.com",
        role="admin",
    )


@pytest.fixture
def first_login_user(db):
    return User.objects.create_user(
        username="firstlogin",
        password="TemporaryPassword123!",
        first_name="Piotr",
        last_name="Testowy",
        role="radiologist",
        is_first_login=True,
    )


@pytest.fixture
def blocked_user(db):
    return User.objects.create_user(
        username="blocked",
        password="BlockedPassword123!",
        role="radiologist",
        is_active=False,
    )


@pytest.fixture
def authenticated_client(api_client, radiologist):
    api_client.force_authenticate(user=radiologist)
    return api_client


@pytest.fixture
def researcher_client(api_client, researcher):
    api_client.force_authenticate(user=researcher)
    return api_client


@pytest.fixture
def admin_client(api_client, admin_user):
    api_client.force_authenticate(user=admin_user)
    return api_client
