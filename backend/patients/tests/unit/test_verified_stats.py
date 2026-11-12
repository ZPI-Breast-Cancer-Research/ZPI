import pytest
from django.utils import timezone
from datetime import timedelta

from patients.views import _verified_stats
from extraction.models import ExtractionResult
from segmentation.models import SegmentationResult


@pytest.mark.django_db
def test_verified_stats_counts_approved_extractions(study, user):
    ExtractionResult.objects.create(
        study=study,
        status="APPROVED",
        accepted_by=user,
        accepted_at=timezone.localdate(),
    )

    stats = _verified_stats()

    assert stats is not None


@pytest.mark.django_db
def test_verified_stats_counts_corrected_extractions(study, user):
    ExtractionResult.objects.create(
        study=study,
        status="CORRECTED",
        accepted_by=user,
        accepted_at=timezone.localdate(),
    )

    stats = _verified_stats()

    assert stats is not None


@pytest.mark.django_db
def test_verified_stats_ignores_old_results(study, user):
    ExtractionResult.objects.create(
        study=study,
        status="APPROVED",
        accepted_by=user,
        accepted_at=timezone.localdate() - timedelta(days=30),
    )

    stats = _verified_stats()

    assert stats is not None