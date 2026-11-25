"""POST approve-mask/ with the corrected mask as a DICOM SEG (ADR 0004, T-06b)."""

from io import BytesIO
from unittest import mock

import pytest
from audit.models import AuditLog
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from extraction.models import StatusChoices
from pydicom.dataset import Dataset, FileMetaDataset
from pydicom.uid import ExplicitVRLittleEndian, generate_uid
from rest_framework import status
from segmentation.models import SegmentationResult

STUDY_UID = "1.2.826.0.1.3680043.8.498.1"
SEG_SOP_CLASS = "1.2.840.10008.5.1.4.1.1.66.4"


def _seg_bytes(*, study_uid=STUDY_UID, modality="SEG") -> tuple[bytes, Dataset]:
    """A DICOM header with what the API reads; the pixels are the worker's business."""
    ds = Dataset()
    ds.SOPClassUID = SEG_SOP_CLASS
    ds.SOPInstanceUID = generate_uid()
    ds.StudyInstanceUID = study_uid
    ds.SeriesInstanceUID = generate_uid()
    ds.Modality = modality
    ds.file_meta = FileMetaDataset()
    ds.file_meta.MediaStorageSOPClassUID = ds.SOPClassUID
    ds.file_meta.MediaStorageSOPInstanceUID = ds.SOPInstanceUID
    ds.file_meta.TransferSyntaxUID = ExplicitVRLittleEndian
    buffer = BytesIO()
    ds.save_as(buffer, enforce_file_format=True)
    return buffer.getvalue(), ds


def _post(client, study, data: bytes):
    return client.post(
        reverse("approve-mask", kwargs={"study_id": study.orthanc_path}),
        {"seg": SimpleUploadedFile("mask.dcm", data, content_type="application/dicom")},
        format="multipart",
    )


@pytest.fixture
def orthanc():
    with mock.patch("segmentation.approval.OrthancClient") as client_class:
        client = client_class.return_value
        client.study_instance_uid.return_value = STUDY_UID
        yield client


@pytest.fixture
def send_task():
    with mock.patch("segmentation.approval.current_app.send_task") as send:
        yield send


@pytest.fixture
def completed(study):
    return SegmentationResult.objects.create(study=study, status=StatusChoices.COMPLETED)


@pytest.mark.django_db
def test_a_corrected_seg_is_stored_approved_and_queued_for_conversion(
    authenticated_client,
    reviewer,
    study,
    completed,
    orthanc,
    send_task,
    django_capture_on_commit_callbacks,
):
    # Arrange
    data, seg = _seg_bytes()

    # Act
    with django_capture_on_commit_callbacks(execute=True):
        response = _post(authenticated_client, study, data)

    # Assert
    assert response.status_code == status.HTTP_200_OK
    completed.refresh_from_db()
    assert completed.status == StatusChoices.CORRECTED
    assert completed.accepted_by == reviewer
    assert completed.approved_seg_series_uid == seg.SeriesInstanceUID
    assert completed.approved_seg_sop_uid == seg.SOPInstanceUID
    orthanc.upload_dicom_bytes.assert_called_once_with(data)
    send_task.assert_called_once_with(
        "segmentation.correction_from_dicom_seg", kwargs={"result_id": completed.pk}
    )
    assert AuditLog.objects.get().detail == "corrected"


@pytest.mark.django_db
def test_a_seg_of_another_study_is_refused_before_orthanc(
    authenticated_client, study, completed, orthanc, send_task
):
    data, _ = _seg_bytes(study_uid="1.2.3.999")

    response = _post(authenticated_client, study, data)

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert response.json()["code"] == "seg_wrong_study"
    orthanc.upload_dicom_bytes.assert_not_called()
    completed.refresh_from_db()
    assert completed.status == StatusChoices.COMPLETED
    assert not AuditLog.objects.exists()


@pytest.mark.parametrize(
    "data",
    [b"not a dicom file", _seg_bytes(modality="MR")[0]],
    ids=["not-dicom", "not-seg"],
)
@pytest.mark.django_db
def test_a_file_that_is_not_a_seg_is_refused(
    authenticated_client, study, completed, orthanc, send_task, data
):
    response = _post(authenticated_client, study, data)

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert response.json()["code"] == "invalid_seg"
    orthanc.upload_dicom_bytes.assert_not_called()


@pytest.mark.parametrize("mask_status", [StatusChoices.PROCESSING, StatusChoices.APPROVED])
@pytest.mark.django_db
def test_a_mask_not_waiting_for_review_refuses_the_seg_before_orthanc(
    authenticated_client, study, orthanc, send_task, mask_status
):
    SegmentationResult.objects.create(study=study, status=mask_status)
    data, _ = _seg_bytes()

    response = _post(authenticated_client, study, data)

    assert response.status_code == status.HTTP_409_CONFLICT
    orthanc.upload_dicom_bytes.assert_not_called()
    send_task.assert_not_called()


@pytest.mark.django_db
def test_orthanc_down_saves_nothing(authenticated_client, study, completed, orthanc, send_task):
    from patients.errors import OrthancUnavailable

    orthanc.upload_dicom_bytes.side_effect = OrthancUnavailable("down")
    data, _ = _seg_bytes()

    response = _post(authenticated_client, study, data)

    assert response.status_code == status.HTTP_503_SERVICE_UNAVAILABLE
    completed.refresh_from_db()
    assert completed.status == StatusChoices.COMPLETED
    assert completed.approved_seg_series_uid == ""
    send_task.assert_not_called()
    assert not AuditLog.objects.exists()


@pytest.mark.django_db
def test_approving_without_a_file_works_as_before(
    authenticated_client, study, completed, orthanc, send_task
):
    response = authenticated_client.post(
        reverse("approve-mask", kwargs={"study_id": study.orthanc_path}),
        {"mask": "confirmed"},
        format="json",
    )

    assert response.status_code == status.HTTP_200_OK
    completed.refresh_from_db()
    assert completed.status == StatusChoices.APPROVED
    orthanc.upload_dicom_bytes.assert_not_called()
    send_task.assert_not_called()
