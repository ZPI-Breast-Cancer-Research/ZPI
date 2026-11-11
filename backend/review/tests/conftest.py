import pytest
from rest_framework.test import APIClient
from django.contrib.auth import get_user_model

from patients.models import Study
from segmentation.models import SegmentationResult
from extraction.models import ExtractionResult, StatusChoices


User = get_user_model()


@pytest.fixture
def api_client():
    return APIClient()


@pytest.fixture
def reviewer(db):
    return User.objects.create_user(
        username="reviewer",
        password="TestPassword123!",
        first_name="Jan",
        last_name="Kowalski",
        role="radiologist",
    )


@pytest.fixture
def authenticated_client(api_client, reviewer):
    api_client.force_authenticate(user=reviewer)
    return api_client


@pytest.fixture
def study(db):
    return Study.objects.create(
        orthanc_path="orthanc-study-123"
    )


@pytest.fixture
def segmentation(study):
    return SegmentationResult.objects.create(
        study=study,
        status=StatusChoices.COMPLETED,
        uncertainty=0.75,
    )


@pytest.fixture
def extraction(study):
    return ExtractionResult.objects.create(
        study=study,
        status=StatusChoices.COMPLETED,
        uncertainty=0.45,
        generated_report={
            "birads": "4C",
            "size": "12",
            "location": "KGZ",
        },
    )
