"""The original report next to the form, and the audit entries the review actions leave."""

from unittest import mock

import pytest
from django.urls import reverse

from audit.models import AuditLog
from extraction.models import ExtractionResult, StatusChoices
from segmentation.models import SegmentationResult


def _url(name, study):
    return reverse(name, kwargs={"study_id": study.orthanc_path})


@pytest.mark.django_db
def test_report_scan_returns_the_uploaded_original(authenticated_client, study):
    # Arrange
    ExtractionResult.objects.create(
        study=study, status=StatusChoices.COMPLETED, report_path="reports/a/opis.jpg"
    )

    # Act
    with mock.patch("review.views.get_bytes", return_value=b"jpeg-bytes") as get_bytes:
        response = authenticated_client.get(_url("review-report-scan", study))

    # Assert
    assert response.status_code == 200
    assert response["Content-Type"] == "image/jpeg"
    assert response.content == b"jpeg-bytes"
    get_bytes.assert_called_once_with("reports", "reports/a/opis.jpg")


@pytest.mark.django_db
def test_report_scan_is_404_without_an_uploaded_file(authenticated_client, study):
    ExtractionResult.objects.create(study=study, status=StatusChoices.COMPLETED)

    response = authenticated_client.get(_url("review-report-scan", study))

    assert response.status_code == 404


@pytest.mark.django_db
def test_report_scan_is_404_when_storage_has_no_file(authenticated_client, study):
    ExtractionResult.objects.create(
        study=study, status=StatusChoices.COMPLETED, report_path="reports/a/opis.jpg"
    )

    with mock.patch("review.views.get_bytes", side_effect=Exception("NoSuchKey")):
        response = authenticated_client.get(_url("review-report-scan", study))

    assert response.status_code == 404


@pytest.mark.django_db
def test_approve_case_leaves_mask_and_form_entries(authenticated_client, study, reviewer):
    # Arrange
    SegmentationResult.objects.create(study=study, status=StatusChoices.COMPLETED)
    ExtractionResult.objects.create(study=study, status=StatusChoices.COMPLETED)

    # Act
    authenticated_client.post(_url("approve-case", study), {"mask": "corrected"}, format="json")

    # Assert
    entries = {e.kind: e for e in AuditLog.objects.all()}
    assert set(entries) == {"mask_approved", "form_approved"}
    assert entries["mask_approved"].detail == "corrected"
    assert entries["mask_approved"].user == reviewer
    assert entries["mask_approved"].object == f"#{str(study.id).zfill(4)}"


@pytest.mark.django_db
def test_reopen_case_leaves_entries_only_for_what_was_approved(authenticated_client, study):
    # Arrange
    SegmentationResult.objects.create(study=study, status=StatusChoices.APPROVED)
    ExtractionResult.objects.create(study=study, status=StatusChoices.COMPLETED)

    # Act
    authenticated_client.post(_url("reopen-case", study))

    # Assert
    assert list(AuditLog.objects.values_list("kind", flat=True)) == ["mask_unapproved"]


@pytest.mark.django_db
def test_an_action_that_changes_nothing_leaves_no_entry(authenticated_client, study):
    SegmentationResult.objects.create(study=study, status=StatusChoices.PENDING)

    authenticated_client.post(_url("approve-mask", study), {"mask": "confirmed"}, format="json")

    assert not AuditLog.objects.exists()
