"""A study without an uploaded report gets the form filled in by the radiologist (source =
manual): stored without a worker, shown like a report, left out of the extraction statistics."""

from unittest import mock

import pytest
from audit.models import AuditLog
from django.urls import reverse
from extraction.models import ExtractionResult, SourceChoices, StatusChoices
from mlops.models import ModelVersion
from segmentation.models import SegmentationResult

FORM = {
    "modalnosci": ["mri"],
    "zmiany": [{"wymiary": {"wartosci": [14], "jednostka": "mm"}}],
    "wniosek": {"birads": "4"},
}


def _approve_form(client, study, payload):
    return client.post(
        reverse("approve-form", kwargs={"study_id": study.orthanc_path}), payload, format="json"
    )


@pytest.mark.django_db
def test_saving_the_form_without_a_report_creates_a_manual_one(
    authenticated_client, reviewer, study
):
    # Act
    response = _approve_form(
        authenticated_client,
        study,
        {"report": FORM, "fields": {"wniosek.birads": "corrected"}},
    )

    # Assert
    assert response.status_code == 200
    report = ExtractionResult.objects.get(study=study)
    assert report.source == SourceChoices.MANUAL
    # nothing to correct: there was no model answer
    assert report.status == StatusChoices.APPROVED
    assert report.report_path is None
    assert report.accepted_report == FORM
    assert (report.accepted_by, report.requested_by) == (reviewer, reviewer)
    assert report.assigned_at is not None
    assert AuditLog.objects.get().detail == "Form filled in by hand"


@pytest.mark.django_db
def test_without_a_form_nothing_is_created(authenticated_client, study):
    response = _approve_form(authenticated_client, study, {})

    assert response.status_code == 200
    assert not ExtractionResult.objects.exists()


@pytest.mark.django_db
def test_sending_the_manual_form_again_updates_it_and_keeps_it_approved(
    authenticated_client, study
):
    _approve_form(authenticated_client, study, {"report": FORM})
    changed = {**FORM, "wniosek": {"birads": "5"}}

    _approve_form(
        authenticated_client, study, {"report": changed, "fields": {"wniosek.birads": "corrected"}}
    )

    report = ExtractionResult.objects.get(study=study)
    assert report.accepted_report == changed
    assert report.status == StatusChoices.APPROVED


@pytest.mark.django_db
def test_approving_the_case_without_a_report_stores_the_manual_form(authenticated_client, study):
    SegmentationResult.objects.create(study=study, status=StatusChoices.COMPLETED)

    response = authenticated_client.post(
        reverse("approve-case", kwargs={"study_id": study.orthanc_path}),
        {"mask": "confirmed", "report": FORM},
        format="json",
    )

    assert response.status_code == 200
    assert ExtractionResult.objects.get(study=study).source == SourceChoices.MANUAL
    assert SegmentationResult.objects.get(study=study).status == StatusChoices.APPROVED


@pytest.mark.django_db
def test_the_case_shows_a_manual_form_without_waiting_for_a_worker(authenticated_client, study):
    # Arrange
    _approve_form(authenticated_client, study, {"report": FORM})

    # Act
    with mock.patch("review.views.OrthancClient") as orthanc:
        orthanc.return_value.list_studies.return_value = []
        response = authenticated_client.get(
            reverse("review-case-detail", kwargs={"study_id": study.orthanc_path})
        )

    # Assert
    assert response.status_code == 200
    assert response.data["reportSource"] == "manual"
    report = response.data["report"]
    assert report["originalUrl"] is None
    assert report["result"]["status"] == "ok"
    assert report["result"]["source"] == "manual"
    assert report["result"]["data"] == FORM
    assert report["result"]["text"] == ""
    assert response.data["measurements"]["sizeInReport"] == 14.0


@pytest.mark.django_db
def test_manual_forms_are_left_out_of_the_extraction_statistics(api_client, study, db):
    from django.contrib.auth import get_user_model

    researcher = get_user_model().objects.create_user(
        username="researcher", password="TestPassword123!", role="researcher"
    )
    api_client.force_authenticate(user=researcher)
    # the statistics follow the extraction version in use when there is one
    ModelVersion.objects.filter(module="ext").delete()
    ExtractionResult.objects.create(
        study=study,
        status=StatusChoices.APPROVED,
        generated_report={"birads": "3"},
        accepted_report={"birads": "3"},
    )
    ExtractionResult.objects.create(
        study=study,
        source=SourceChoices.MANUAL,
        status=StatusChoices.APPROVED,
        accepted_report={"birads": "4"},
    )

    response = api_client.get(reverse("extraction-overview"))

    assert response.json()["examplePool"] == 1
