from datetime import date, datetime, timedelta
from types import SimpleNamespace
from unittest import mock

import pytest
from django.utils import timezone

from mlops import views
from mlops.models import ModelVersion
from segmentation.models import SegmentationResult, StatusChoices


def test_iso_returns_formatted_date():
    assert views._iso(date(2025, 5, 10)) == "2025-05-10"


def test_iso_returns_none():
    assert views._iso(None) is None


def test_full_name_returns_none():
    assert views._full_name(None) is None


def test_full_name_returns_first_and_last_name():
    user = SimpleNamespace(
        first_name="Jan",
        last_name="Kowalski",
        username="jan"
    )

    assert views._full_name(user) == "Jan Kowalski"


def test_full_name_falls_back_to_username():
    user = SimpleNamespace(
        first_name="",
        last_name="",
        username="jan"
    )

    assert views._full_name(user) == "jan"


@pytest.mark.django_db
def test_corrected_share_returns_none_when_no_verified_results(study):
    queryset = SegmentationResult.objects.filter(study=study)

    assert views._corrected_share(queryset) is None


@pytest.mark.django_db
def test_corrected_share_calculates_correct_percentage(study):
    SegmentationResult.objects.create(
        study=study,
        status=StatusChoices.APPROVED
    )

    SegmentationResult.objects.create(
        study=study,
        status=StatusChoices.CORRECTED
    )

    SegmentationResult.objects.create(
        study=study,
        status=StatusChoices.CORRECTED
    )

    SegmentationResult.objects.create(
        study=study,
        status=StatusChoices.PENDING
    )

    queryset = SegmentationResult.objects.filter(study=study)

    assert views._corrected_share(queryset) == 0.67


@pytest.mark.django_db
def test_next_retraining_returns_correct_data(settings):
    settings.RETRAIN_HOUR = 2
    settings.RETRAIN_THRESHOLD = 50

    now = timezone.make_aware(
        datetime(2025, 5, 10, 1, 0)
    )

    with mock.patch.object(
        views.timezone,
        "localtime",
        return_value=now
    ):
        result = views._next_retraining(
            ModelVersion.objects.none()
        )

    assert result["threshold"] == 50
    assert result["window"] == "2025-05-10T02:00"
    assert result["corrections"] == 0


@pytest.mark.django_db
def test_next_retraining_moves_window_to_next_day(settings):
    settings.RETRAIN_HOUR = 2

    now = timezone.make_aware(
        datetime(2025, 5, 10, 3, 0)
    )

    with mock.patch.object(
        views.timezone,
        "localtime",
        return_value=now
    ):
        result = views._next_retraining(
            ModelVersion.objects.none()
        )

    assert result["window"] == "2025-05-11T02:00"


@pytest.mark.django_db
def test_weekly_corrected_returns_empty_list():
    result = views._weekly_corrected(
        ModelVersion.objects.none()
    )

    assert result == []
