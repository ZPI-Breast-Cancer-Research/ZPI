from unittest import mock
import pytest

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