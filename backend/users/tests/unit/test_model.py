# users/tests/test_model.py

import pytest
from django.contrib.auth import get_user_model

User = get_user_model()


@pytest.mark.django_db
def test_user_default_role():
    user = User.objects.create_user(
        username="defaultrole",
        password="Password123!",
    )

    assert user.role == "radiologist"


@pytest.mark.django_db
def test_user_default_first_login_is_false():
    user = User.objects.create_user(
        username="normaluser",
        password="Password123!",
    )

    assert user.is_first_login is False


@pytest.mark.django_db
def test_user_superuser_gets_admin_role():
    user = User.objects.create_superuser(
        username="superadmin",
        password="Password123!",
        email="superadmin@example.com",
    )

    assert user.is_superuser is True
    assert user.role == "admin"


@pytest.mark.django_db
def test_user_string_representation(radiologist):
    assert str(radiologist) == "radiologist (radiologist)"


@pytest.mark.django_db
def test_user_pwz_can_be_empty():
    user = User.objects.create_user(
        username="nopwz",
        password="Password123!",
    )

    assert user.pwz is None


@pytest.mark.django_db
def test_user_pwz_must_be_unique(radiologist):
    with pytest.raises(Exception):
        User.objects.create_user(
            username="anotheruser",
            password="Password123!",
            pwz=radiologist.pwz,
        )
