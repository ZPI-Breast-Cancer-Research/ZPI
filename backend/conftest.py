import pytest


@pytest.fixture(autouse=True)
def fast_password_hasher(settings):
    """The production hasher takes ~2 s per user; tests only need passwords to round-trip."""
    settings.PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]
