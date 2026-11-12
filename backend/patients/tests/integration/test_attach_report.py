from unittest import mock
import pytest
from django.urls import reverse
from django.utils import timezone

from patients.models import Study
from extraction.models import ExtractionResult


@pytest.mark.django_db
def test_attach_report_to_study_returns_404_for_unknown_study(
    authenticated_client,
):
    response = authenticated_client.post(
        "/api/studies/unknown-study/attach-report/",
        {},
        format="multipart",
    )

    assert response.status_code == 404


@pytest.mark.django_db
@mock.patch("patients.views.current_app.send_task")
def test_attach_existing_report_assigns_report_to_study(
    send_task,
    authenticated_client,
    study,
    unassigned_extraction_result,
):
    response = authenticated_client.post(
        f"/api/studies/{study.orthanc_path}/attach-existing-report/",
        {
            "report_id": unassigned_extraction_result.id,
        },
        format="json",
    )

    assert response.status_code in (200, 201)

    unassigned_extraction_result.refresh_from_db()

    assert unassigned_extraction_result.study == study
    send_task.assert_not_called()


@pytest.mark.django_db
def test_attach_existing_report_does_not_change_other_report(
    authenticated_client,
    study,
    extraction_result,
):
    response = authenticated_client.post(
        f"/api/studies/{study.orthanc_path}/attach-existing-report/",
        {
            "report_id": 999999,
        },
        format="json",
    )

    assert response.status_code == 404

    extraction_result.refresh_from_db()
    assert extraction_result.study == study

@pytest.mark.django_db
@mock.patch("patients.views._orthanc_studies")
def test_attached_older_report_becomes_the_active_one(
    orthanc_studies, authenticated_client, study, unassigned_extraction_result
):
    # Arrange: the study already has a report newer (by id) than the one being assigned
    ExtractionResult.objects.create(study=study, status="COMPLETED")
    unassigned_extraction_result.status = "FAILED"
    unassigned_extraction_result.save()
    orthanc_studies.return_value = [{"orthanc_id": study.orthanc_path}]

    # Act
    authenticated_client.post(
        f"/api/studies/{study.orthanc_path}/attach-existing-report/",
        {"report_id": unassigned_extraction_result.id},
        format="json",
    )
    response = authenticated_client.get(reverse("study-list"))

    # Assert
    assert response.status_code == 200
    assert response.data[0]["extraction_status"] == "FAILED"


@pytest.mark.django_db
def test_active_report_prefers_an_assigned_one_over_a_row_from_before_assigned_at(study):
    # Arrange: a newer row (higher id) without assigned_at, as left by the migration backfill gap
    assigned = ExtractionResult.objects.create(study=study, assigned_at=timezone.now())
    ExtractionResult.objects.create(study=study, assigned_at=None)

    # Act
    active = ExtractionResult.objects.filter(study=study).active()
    ordered = list(ExtractionResult.objects.filter(study=study).oldest_assigned_first())

    # Assert
    assert active == assigned
    assert ordered[-1] == assigned
