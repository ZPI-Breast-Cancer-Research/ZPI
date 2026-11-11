import pytest
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient

from mlops.models import ModelVersion
from patients.models import Study


@pytest.fixture
def user(db):
    User = get_user_model()
    return User.objects.create_user(
        username="testuser",
        password="testpassword",
        role = "researcher"
    )


@pytest.fixture
def authenticated_client(user):
    client = APIClient()
    client.force_authenticate(user=user)
    return client


@pytest.fixture
def study(db):
    return Study.objects.create(
        orthanc_path="test-study-123"
    )


@pytest.fixture
def production_model(db):
    return ModelVersion.objects.create(
        module=ModelVersion.ModuleChoices.SEG,
        name="segmentation",
        version="1.0",
        status=ModelVersion.StatusChoices.PRODUCTION,
        dice=0.85,
    )


@pytest.fixture
def candidate_model(db):
    return ModelVersion.objects.create(
        module=ModelVersion.ModuleChoices.SEG,
        name="segmentation",
        version="2.0",
        status=ModelVersion.StatusChoices.CANDIDATE,
        dice=0.90,
    )

@pytest.fixture
def api_client():
    return APIClient()