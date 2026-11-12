"""Report files the extractor cannot read are refused at upload; a failed extraction shows on the
dashboard."""

from unittest import mock

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from extraction.models import ExtractionResult, StatusChoices


def report(name: str) -> SimpleUploadedFile:
    return SimpleUploadedFile(
        name, b"Opis badania: zmiana 5 mm", content_type="application/octet-stream"
    )


@pytest.mark.django_db
@pytest.mark.parametrize("name", ["opis.pdf", "opis.docx", "opis"])
@mock.patch("patients.views.put_bytes")
def test_import_refuses_unsupported_report_type(put_bytes, authenticated_client, name):
    # Act
    response = authenticated_client.post(
        reverse("study-import"), {"report": report(name)}, format="multipart"
    )

    # Assert
    assert response.status_code == 400
    assert response.data["code"] == "unsupported_report_type"
    assert ExtractionResult.objects.count() == 0
    put_bytes.assert_not_called()


@pytest.mark.django_db
@mock.patch("patients.views.OrthancClient")
@mock.patch("patients.views._check_archive", return_value=None)
def test_import_refuses_bad_report_before_the_archive_goes_to_orthanc(
    check_archive, orthanc_client, authenticated_client
):
    # Act
    response = authenticated_client.post(
        reverse("study-import"),
        {"archives": SimpleUploadedFile("study.zip", b"zip"), "report": report("opis.pdf")},
        format="multipart",
    )

    # Assert
    assert response.status_code == 400
    orthanc_client.return_value.upload_dicom_zip.assert_not_called()


@pytest.mark.django_db
@pytest.mark.parametrize("name", ["opis.txt", "skan.JPG", "skan.jpeg", "skan.png"])
@mock.patch("patients.views.current_app.send_task")
@mock.patch("patients.views.put_bytes")
def test_import_accepts_supported_report_types(
    put_bytes, send_task, authenticated_client, django_capture_on_commit_callbacks, name
):
    # Act
    with django_capture_on_commit_callbacks(execute=True):
        response = authenticated_client.post(
            reverse("study-import"), {"report": report(name)}, format="multipart"
        )

    # Assert
    assert response.status_code in (200, 201)
    assert ExtractionResult.objects.count() == 1
    send_task.assert_called_once()


@pytest.mark.django_db
@mock.patch("patients.views.put_bytes")
def test_attach_refuses_unsupported_report_type(put_bytes, authenticated_client, study):
    # Act
    response = authenticated_client.post(
        f"/api/studies/{study.orthanc_path}/attach-report/",
        {"report": report("opis.pdf")},
        format="multipart",
    )

    # Assert
    assert response.status_code == 400
    assert response.data["code"] == "unsupported_report_type"
    assert not ExtractionResult.objects.filter(study=study).exists()
    put_bytes.assert_not_called()


@pytest.mark.django_db
@mock.patch("patients.views._orthanc_studies")
def test_dashboard_lists_failed_extraction_as_processing_error(
    orthanc_studies, authenticated_client, study
):
    # Arrange
    orthanc_studies.return_value = [{"orthanc_id": study.orthanc_path}]
    ExtractionResult.objects.create(study=study, status=StatusChoices.FAILED, error="LLM: down")

    # Act
    response = authenticated_client.get(reverse("dashboard-view"))

    # Assert
    assert response.status_code == 200
    number = str(study.id).zfill(4)  # the study number of the review screens
    assert {"kind": "processing_error", "subject": number, "href": "/badania"} in response.data[
        "attention"
    ]
