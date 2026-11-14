"""Deleting a study removes it from Orthanc, storage and the database, and is refused for a
verified one."""

from unittest import mock

import pytest
from django.urls import reverse

from audit.models import AuditLog
from extraction.models import ExtractionResult, StatusChoices
from patients.models import Study
from patients.orthanc_client import OrthancUnavailable
from segmentation.models import SegmentationResult


def _delete(client, study):
    return client.delete(reverse("study-delete", kwargs={"orthanc_id": study.orthanc_path}))


@pytest.fixture
def orthanc():
    with mock.patch("patients.views.OrthancClient") as client:
        yield client.return_value


@pytest.fixture
def storage():
    with (
        mock.patch("patients.views.delete_prefix") as prefix,
        mock.patch("patients.views.delete_object") as obj,
    ):
        yield mock.Mock(prefix=prefix, obj=obj)


@pytest.mark.django_db
def test_delete_removes_dicom_files_and_rows(
    authenticated_client, study, segmentation_result, orthanc, storage
):
    # Arrange
    ExtractionResult.objects.create(study=study, report_path="reports/abc/opis.jpg")
    ExtractionResult.objects.create(study=study)  # no file, nothing to delete
    study_id = study.id

    # Act
    response = _delete(authenticated_client, study)

    # Assert
    assert response.status_code == 204
    orthanc.delete_study.assert_called_once_with("orthanc-study-123")
    storage.prefix.assert_called_once_with("masks", f"{study_id}/")
    storage.obj.assert_called_once_with("reports", "reports/abc/opis.jpg")
    assert not Study.objects.filter(pk=study_id).exists()
    assert not SegmentationResult.objects.filter(study_id=study_id).exists()
    assert not ExtractionResult.objects.filter(study_id=study_id).exists()


@pytest.mark.django_db
def test_delete_leaves_an_audit_entry_without_patient_data(
    authenticated_client, study, orthanc, storage
):
    study_id = study.id

    _delete(authenticated_client, study)

    entry = AuditLog.objects.get()
    assert (entry.kind, entry.object) == ("study_deleted", f"#{str(study_id).zfill(4)}")
    assert "orthanc-study-123" not in (entry.detail or "")


@pytest.mark.django_db
def test_other_studies_and_their_masks_stay(authenticated_client, study, orthanc, storage):
    other = Study.objects.create(orthanc_path="other-study")
    SegmentationResult.objects.create(study=other, status=StatusChoices.COMPLETED)

    _delete(authenticated_client, study)

    assert Study.objects.filter(pk=other.pk).exists()
    assert SegmentationResult.objects.filter(study=other).exists()
    # a prefix with the slash cannot hit "21/" when deleting study 2
    assert storage.prefix.call_args.args[1].endswith("/")


@pytest.mark.django_db
@pytest.mark.parametrize("model", [SegmentationResult, ExtractionResult])
@pytest.mark.parametrize("verified", [StatusChoices.APPROVED, StatusChoices.CORRECTED])
def test_a_verified_study_is_refused_and_nothing_is_touched(
    authenticated_client, study, orthanc, storage, model, verified
):
    model.objects.create(study=study, status=verified)

    response = _delete(authenticated_client, study)

    assert response.status_code == 409
    assert response.data["code"] == "verified"
    assert Study.objects.filter(pk=study.pk).exists()
    orthanc.delete_study.assert_not_called()
    storage.prefix.assert_not_called()
    assert not AuditLog.objects.exists()


@pytest.mark.django_db
def test_after_taking_back_the_verification_it_can_be_deleted(
    authenticated_client, study, orthanc, storage
):
    SegmentationResult.objects.create(study=study, status=StatusChoices.COMPLETED)

    assert _delete(authenticated_client, study).status_code == 204


@pytest.mark.django_db
def test_when_orthanc_fails_the_rows_stay_so_it_can_be_repeated(
    authenticated_client, study, orthanc, storage
):
    orthanc.delete_study.side_effect = OrthancUnavailable("down")

    response = _delete(authenticated_client, study)

    assert response.status_code in (502, 503)
    assert Study.objects.filter(pk=study.pk).exists()
    storage.prefix.assert_not_called()
    assert not AuditLog.objects.exists()


@pytest.mark.django_db
def test_when_storage_fails_the_rows_stay_so_it_can_be_repeated(
    authenticated_client, study, orthanc, storage
):
    storage.prefix.side_effect = RuntimeError("minio down")

    response = _delete(authenticated_client, study)

    assert response.status_code == 502
    assert response.data["code"] == "delete_failed"
    assert Study.objects.filter(pk=study.pk).exists()


@pytest.mark.django_db
def test_an_unknown_study_is_404(authenticated_client, orthanc, storage):
    response = authenticated_client.delete(reverse("study-delete", kwargs={"orthanc_id": "nope"}))

    assert response.status_code == 404
    orthanc.delete_study.assert_not_called()


@pytest.mark.django_db
def test_a_researcher_cannot_delete(researcher_client, study, orthanc, storage):
    response = _delete(researcher_client, study)

    assert response.status_code == 403
    assert Study.objects.filter(pk=study.pk).exists()


@pytest.mark.django_db
def test_an_anonymous_user_cannot_delete(api_client, study, orthanc, storage):
    response = _delete(api_client, study)

    assert response.status_code in (401, 403)
    assert Study.objects.filter(pk=study.pk).exists()
