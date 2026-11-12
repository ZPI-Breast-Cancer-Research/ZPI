"""Only the admin reads the audit log (the Settings page is theirs)."""

import pytest
from django.urls import reverse
from rest_framework.test import APIClient

from audit.models import AuditLog
from users.models import User


def _client(role):
    user = User.objects.create_user(username=f"u-{role}", password="TestPassword123!", role=role)
    client = APIClient()
    client.force_authenticate(user=user)
    return client, user


@pytest.mark.django_db
def test_admin_reads_the_latest_entries_first():
    # Arrange
    client, admin = _client("admin")
    AuditLog.objects.create(user=admin, kind="mask_approved", object="#0001")
    AuditLog.objects.create(user=admin, kind="form_approved", object="#0001")

    # Act
    response = client.get(reverse("audit-logs-list"))

    # Assert
    assert response.status_code == 200
    assert [e["kind"] for e in response.data] == ["form_approved", "mask_approved"]
    assert response.data[0]["login"] == "u-admin"


@pytest.mark.django_db
@pytest.mark.parametrize("role", ["radiologist", "researcher"])
def test_other_roles_cannot_read_the_log(role):
    client, _ = _client(role)

    response = client.get(reverse("audit-logs-list"))

    assert response.status_code == 403


@pytest.mark.django_db
def test_anonymous_cannot_read_the_log():
    response = APIClient().get(reverse("audit-logs-list"))

    assert response.status_code in (401, 403)
