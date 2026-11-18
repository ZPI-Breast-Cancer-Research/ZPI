from unittest import mock

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from extraction.models import ExtractionResult
from patients.models import Study
from segmentation.models import SegmentationResult


@pytest.mark.django_db
@mock.patch("patients.views._check_archive", return_value=(False, "No archive"))
def test_import_without_files_returns_bad_request(
    mock_check_archive,
    authenticated_client,
):
    response = authenticated_client.post(
        reverse("study-import"),
        {},
        format="multipart",
    )

    assert response.status_code == 400


@pytest.mark.django_db
@mock.patch("patients.views._check_archive", return_value=(False, "Invalid archive"))
def test_import_rejects_invalid_archive(
    mock_check_archive,
    authenticated_client,
):
    response = authenticated_client.post(
        reverse("study-import"),
        {"dicom_file": "invalid"},
        format="multipart",
    )

    assert response.status_code == 400


@pytest.mark.django_db
@mock.patch("patients.views._check_archive", return_value=(False, "Invalid archive"))
def test_import_does_not_create_study_when_archive_is_invalid(
    mock_check_archive,
    authenticated_client,
):
    response = authenticated_client.post(
        reverse("study-import"),
        {"dicom_file": "invalid"},
        format="multipart",
    )

    assert response.status_code == 400
    assert Study.objects.count() == 0


@pytest.mark.django_db
@mock.patch("patients.views.current_app.send_task")
@mock.patch("patients.views.put_bytes", return_value="reports/test.json")
def test_import_of_a_report_alone_only_stores_it(
    mock_put_bytes,
    send_task,
    authenticated_client,
    django_capture_on_commit_callbacks,
):
    report_file = SimpleUploadedFile(
        "test_report.txt",
        b"Example diagnosis",
        content_type="text/plain",
    )

    with django_capture_on_commit_callbacks(execute=True) as callbacks:
        response = authenticated_client.post(
            reverse("study-import"),
            {
                "report": report_file,
            },
            format="multipart",
        )

    assert response.status_code in (200, 201)
    assert ExtractionResult.objects.count() == 1

    result = ExtractionResult.objects.first()

    # nothing is computed until the report is assigned or someone orders it
    assert result.study is None
    assert result.status == "UPLOADED"
    assert result.requested_by is None
    assert callbacks == []
    send_task.assert_not_called()


@pytest.mark.django_db
@mock.patch("patients.views.current_app.send_task")
@mock.patch("patients.views.put_bytes", return_value="reports/test.json")
def test_extraction_task_is_not_sent_before_transaction_commit(
    mock_put_bytes,
    send_task,
    authenticated_client,
    study,
    django_capture_on_commit_callbacks,
):
    report_file = SimpleUploadedFile(
        "test_report.txt",
        b"Example",
        content_type="text/plain",
    )

    with django_capture_on_commit_callbacks(execute=False) as callbacks:
        response = authenticated_client.post(
            f"/api/studies/{study.orthanc_path}/attach-report/",
            {
                "report": report_file,
            },
            format="multipart",
        )

        assert response.status_code in (200, 201)
        assert send_task.call_count == 0

    assert len(callbacks) == 1
    assert send_task.call_count == 0


@pytest.mark.django_db
@mock.patch("patients.views.current_app.send_task")
@mock.patch("patients.views.put_bytes", return_value="reports/test.json")
def test_extraction_task_is_sent_after_transaction_commit(
    mock_put_bytes,
    send_task,
    authenticated_client,
    study,
    user,
    django_capture_on_commit_callbacks,
):
    report_file = SimpleUploadedFile(
        "test_report.txt",
        b"Example",
        content_type="text/plain",
    )

    # a report that comes with its study is processed right away
    with django_capture_on_commit_callbacks(execute=True) as callbacks:
        response = authenticated_client.post(
            f"/api/studies/{study.orthanc_path}/attach-report/",
            {
                "report": report_file,
            },
            format="multipart",
        )

    assert response.status_code in (200, 201)
    assert len(callbacks) == 1

    send_task.assert_called_once()
    assert send_task.call_args.args[0] == "extraction.run"
    stored = ExtractionResult.objects.get(study=study)
    assert (stored.status, stored.requested_by) == ("PENDING", user)


@pytest.mark.django_db
@mock.patch("patients.views.current_app.send_task")
@mock.patch("patients.views._check_archive", return_value=(False, "Invalid archive"))
def test_import_does_not_schedule_task_when_request_fails(
    mock_check_archive,
    send_task,
    authenticated_client,
    django_capture_on_commit_callbacks,
):
    with django_capture_on_commit_callbacks(execute=True) as callbacks:
        response = authenticated_client.post(
            reverse("study-import"),
            {},
            format="multipart",
        )

    assert response.status_code == 400
    assert len(callbacks) == 0
    send_task.assert_not_called()


def _dicom_zip() -> SimpleUploadedFile:
    """A ZIP with one minimal DICOM file of one study."""
    import io
    import zipfile

    from pydicom.dataset import Dataset, FileMetaDataset
    from pydicom.uid import ExplicitVRLittleEndian, generate_uid

    ds = Dataset()
    ds.file_meta = FileMetaDataset()
    ds.file_meta.TransferSyntaxUID = ExplicitVRLittleEndian
    ds.file_meta.MediaStorageSOPClassUID = "1.2.840.10008.5.1.4.1.1.4"  # MR Image Storage
    ds.file_meta.MediaStorageSOPInstanceUID = generate_uid()
    ds.StudyInstanceUID = generate_uid()
    dicom = io.BytesIO()
    ds.save_as(dicom, enforce_file_format=True)

    archive = io.BytesIO()
    with zipfile.ZipFile(archive, "w") as zf:
        zf.writestr("IM0001.dcm", dicom.getvalue())
    return SimpleUploadedFile("study.zip", archive.getvalue(), content_type="application/zip")


@mock.patch("patients.views.current_app.send_task")
@mock.patch("patients.views.OrthancClient")
@pytest.mark.django_db
def test_import_creates_the_pending_mask_row_and_schedules_segmentation(
    orthanc, send_task, authenticated_client, django_capture_on_commit_callbacks
):
    # Arrange
    orthanc.return_value.upload_dicom_zip.return_value = {"ParentStudy": "orthanc-new"}

    # Act
    with django_capture_on_commit_callbacks(execute=True):
        response = authenticated_client.post(
            reverse("study-import"), {"archives": _dicom_zip()}, format="multipart"
        )

    # Assert
    assert response.status_code == 201
    study = Study.objects.get(orthanc_path="orthanc-new")
    assert SegmentationResult.objects.get(study=study).status == "PENDING"
    send_task.assert_called_once_with("segmentation.run", kwargs={"study_id": study.id})
