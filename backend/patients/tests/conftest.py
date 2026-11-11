import pytest
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient

from patients.models import Study
from extraction.models import ExtractionResult
from segmentation.models import SegmentationResult


@pytest.fixture
def api_client():
    return APIClient()


@pytest.fixture
def user(db):
    User = get_user_model()
    return User.objects.create_user(
        username="radiologist",
        password="test-password",
        role="radiologist",
    )


@pytest.fixture
def admin_user(db):
    User = get_user_model()
    return User.objects.create_user(
        username="admin",
        password="test-password",
        role="admin",
    )


@pytest.fixture
def researcher_user(db):
    User = get_user_model()
    return User.objects.create_user(
        username="researcher",
        password="test-password",
        role="researcher",
    )


@pytest.fixture
def authenticated_client(api_client, user):
    api_client.force_authenticate(user=user)
    return api_client


@pytest.fixture
def admin_client(api_client, admin_user):
    api_client.force_authenticate(user=admin_user)
    return api_client


@pytest.fixture
def researcher_client(api_client, researcher_user):
    api_client.force_authenticate(user=researcher_user)
    return api_client


@pytest.fixture
def study(db):
    return Study.objects.create(
        orthanc_path="orthanc-study-123",
    )


@pytest.fixture
def extraction_result(db, study):
    return ExtractionResult.objects.create(
        study=study,
        status="COMPLETED",
        uncertainty=0.2,
        generated_report={"diagnosis": "Example"},
    )


@pytest.fixture
def unassigned_extraction_result(db):
    return ExtractionResult.objects.create(
        study=None,
        status="COMPLETED",
        uncertainty=0.3,
        generated_report={"diagnosis": "Unassigned"},
    )


@pytest.fixture
def segmentation_result(db, study):
    return SegmentationResult.objects.create(
        study=study,
        status="COMPLETED",
        uncertainty=0.1,
        generated_path="segmentation/generated/example.nii.gz",
    )
