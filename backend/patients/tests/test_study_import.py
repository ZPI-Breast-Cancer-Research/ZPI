from unittest import mock
import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse

from patients.models import Study
from extraction.models import ExtractionResult


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
def test_import_report_creates_extraction_result(
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

    assert result.study is None
    assert result.status == "PENDING"
    assert len(callbacks) == 1

    send_task.assert_called_once()
    assert send_task.call_args.args[0] == "extraction.run"
    assert send_task.call_args.kwargs["kwargs"]["extraction_id"] == result.id


@pytest.mark.django_db
@mock.patch("patients.views.current_app.send_task")
@mock.patch("patients.views.put_bytes", return_value="reports/test.json")
def test_extraction_task_is_not_sent_before_transaction_commit(
    mock_put_bytes,
    send_task,
    authenticated_client,
    django_capture_on_commit_callbacks,
):
    report_file = SimpleUploadedFile(
        "test_report.txt",
        b"Example",
        content_type="text/plain",
    )

    with django_capture_on_commit_callbacks(execute=False) as callbacks:
        response = authenticated_client.post(
            reverse("study-import"),
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
    django_capture_on_commit_callbacks,
):
    report_file = SimpleUploadedFile(
        "test_report.txt",
        b"Example",
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
    assert len(callbacks) == 1

    send_task.assert_called_once()
    assert send_task.call_args.args[0] == "extraction.run"


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