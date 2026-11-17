"""When a report is processed (on demand, on assignment) and what a closed study refuses
(docs/database.md, "Rules")."""

from datetime import timedelta
from unittest import mock

import pytest
from audit.models import AuditLog
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from django.utils import timezone
from extraction.models import ExtractionResult, SourceChoices, StatusChoices
from patients.models import Study
from segmentation.models import SegmentationResult


@pytest.fixture
def send_task():
    with mock.patch("extraction.processing.current_app.send_task") as send:
        yield send


def _uploaded(**fields) -> ExtractionResult:
    return ExtractionResult.objects.create(
        report_path="reports/abc/opis.txt", source=SourceChoices.TEXT, **fields
    )


def _process(client, report):
    return client.post(reverse("report-process", kwargs={"report_id": report.id}))


def _close(study) -> ExtractionResult:
    """Verify the mask and the active report of the study."""
    SegmentationResult.objects.create(study=study, status=StatusChoices.APPROVED)
    return _uploaded(study=study, status=StatusChoices.APPROVED, assigned_at=timezone.now())


# ---------------------------------------------------------------- on assignment


@pytest.mark.django_db
def test_assigning_a_report_without_a_result_starts_its_processing(
    authenticated_client, user, study, send_task, django_capture_on_commit_callbacks
):
    # Arrange
    report = _uploaded()

    # Act
    with django_capture_on_commit_callbacks(execute=True):
        response = authenticated_client.post(
            f"/api/studies/{study.orthanc_path}/attach-existing-report/",
            {"report_id": report.id},
            format="json",
        )

    # Assert
    assert response.status_code == 200
    report.refresh_from_db()
    assert (report.study, report.status, report.requested_by) == (study, "PENDING", user)
    send_task.assert_called_once_with(
        "extraction.run", kwargs={"extraction_id": report.id, "keys": [report.report_path]}
    )


@pytest.mark.django_db
def test_assigning_a_report_with_a_result_keeps_it(
    authenticated_client, study, send_task, django_capture_on_commit_callbacks
):
    report = _uploaded(status=StatusChoices.COMPLETED, generated_report={"birads": "3"})

    with django_capture_on_commit_callbacks(execute=True):
        authenticated_client.post(
            f"/api/studies/{study.orthanc_path}/attach-existing-report/",
            {"report_id": report.id},
            format="json",
        )

    report.refresh_from_db()
    assert (report.study, report.status) == (study, StatusChoices.COMPLETED)
    assert report.generated_report == {"birads": "3"}
    send_task.assert_not_called()


# ---------------------------------------------------------------- on demand


@pytest.mark.django_db
def test_processing_a_new_report_is_ordered_and_audited(
    authenticated_client, user, send_task, django_capture_on_commit_callbacks
):
    # Arrange
    report = _uploaded()

    # Act
    with django_capture_on_commit_callbacks(execute=True):
        response = _process(authenticated_client, report)

    # Assert
    assert response.status_code == 202
    report.refresh_from_db()
    assert (report.status, report.requested_by) == ("PENDING", user)
    send_task.assert_called_once()
    entry = AuditLog.objects.get()
    assert (entry.kind, entry.object, entry.detail) == (
        "report_processed",
        f"opis #{report.id}",
        "Przetwarzanie",
    )


@pytest.mark.django_db
def test_processing_again_clears_the_previous_result(
    researcher_client, researcher_user, send_task, django_capture_on_commit_callbacks
):
    # Arrange
    report = _uploaded(
        status=StatusChoices.REJECTED,
        generated_report={"birads": "3"},
        accepted_report={"birads": "4"},
        ocr_text="stary",
        uncertainty=0.4,
    )

    # Act
    with django_capture_on_commit_callbacks(execute=True):
        response = _process(researcher_client, report)

    # Assert
    assert response.status_code == 202
    report.refresh_from_db()
    assert report.status == StatusChoices.PENDING
    assert report.requested_by == researcher_user
    assert report.generated_report is report.accepted_report is None
    assert report.ocr_text == ""
    assert report.uncertainty is None
    assert AuditLog.objects.get().detail == "Ponowne przetwarzanie"


@pytest.mark.django_db
def test_a_radiologist_may_process_again_only_after_a_failure(
    authenticated_client, send_task, django_capture_on_commit_callbacks
):
    completed = _uploaded(status=StatusChoices.COMPLETED)
    failed = _uploaded(status=StatusChoices.FAILED, error="LLM down")

    with django_capture_on_commit_callbacks(execute=True):
        refused = _process(authenticated_client, completed)
        allowed = _process(authenticated_client, failed)

    assert refused.status_code == 403
    assert allowed.status_code == 202
    completed.refresh_from_db()
    assert completed.status == StatusChoices.COMPLETED
    send_task.assert_called_once()


@pytest.mark.django_db
@pytest.mark.parametrize(
    "fields, code",
    [
        ({"status": StatusChoices.APPROVED}, "verified"),
        ({"status": StatusChoices.CORRECTED}, "verified"),
        ({"status": StatusChoices.PENDING}, "processing"),
        ({"status": StatusChoices.PROCESSING}, "processing"),
    ],
)
def test_a_verified_or_running_report_is_not_processed(admin_client, send_task, fields, code):
    report = _uploaded(**fields)

    response = _process(admin_client, report)

    assert response.status_code == 409
    assert response.data["code"] == code
    send_task.assert_not_called()


@pytest.mark.django_db
def test_a_manual_form_has_nothing_to_process(admin_client, study, send_task):
    report = ExtractionResult.objects.create(
        study=study, source=SourceChoices.MANUAL, status=StatusChoices.COMPLETED
    )

    response = _process(admin_client, report)

    assert response.status_code == 409
    assert response.data["code"] == "nothing_to_process"


@pytest.mark.django_db
def test_an_anonymous_user_cannot_order_processing(api_client, send_task):
    response = _process(api_client, _uploaded())

    assert response.status_code in (401, 403)


# ---------------------------------------------------------------- a closed study


@pytest.mark.django_db
def test_a_closed_study_accepts_no_new_report(authenticated_client, study, send_task):
    _close(study)
    waiting = _uploaded()

    uploaded = authenticated_client.post(
        f"/api/studies/{study.orthanc_path}/attach-report/",
        {"report": SimpleUploadedFile("opis.txt", b"opis")},
        format="multipart",
    )
    assigned = authenticated_client.post(
        f"/api/studies/{study.orthanc_path}/attach-existing-report/",
        {"report_id": waiting.id},
        format="json",
    )

    assert (uploaded.status_code, uploaded.data["code"]) == (409, "closed")
    assert (assigned.status_code, assigned.data["code"]) == (409, "closed")
    waiting.refresh_from_db()
    assert waiting.study is None


@pytest.mark.django_db
def test_an_older_report_of_a_closed_study_is_not_processed(admin_client, study, send_task):
    older = _uploaded(
        study=study, status=StatusChoices.FAILED, assigned_at=timezone.now() - timedelta(days=1)
    )
    _close(study)

    response = _process(admin_client, older)

    assert (response.status_code, response.data["code"]) == (409, "closed")


@pytest.mark.django_db
@mock.patch("patients.views.put_bytes")
def test_a_verified_mask_without_a_report_can_still_get_one(
    put_bytes, authenticated_client, study, send_task
):
    SegmentationResult.objects.create(study=study, status=StatusChoices.APPROVED)

    response = authenticated_client.post(
        f"/api/studies/{study.orthanc_path}/attach-report/",
        {"report": SimpleUploadedFile("opis.txt", b"opis")},
        format="multipart",
    )

    assert response.status_code == 200
    assert ExtractionResult.objects.filter(study=study).exists()


@pytest.mark.django_db
@mock.patch("patients.views._orthanc_studies")
def test_the_study_list_says_which_study_is_closed(orthanc_studies, authenticated_client, study):
    open_study = Study.objects.create(orthanc_path="open-study")
    SegmentationResult.objects.create(study=open_study, status=StatusChoices.APPROVED)
    _close(study)
    orthanc_studies.return_value = [
        {"orthanc_id": study.orthanc_path},
        {"orthanc_id": open_study.orthanc_path},
    ]

    response = authenticated_client.get(reverse("study-list"))

    closed = {row["orthanc_id"]: row["closed"] for row in response.data}
    assert closed == {study.orthanc_path: True, open_study.orthanc_path: False}
