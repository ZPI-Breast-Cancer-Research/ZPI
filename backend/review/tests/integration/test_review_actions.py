import pytest
from audit.models import AuditLog
from django.urls import reverse
from django.utils import timezone
from extraction.models import ExtractionResult, StatusChoices
from rest_framework import status
from segmentation.models import SegmentationResult

# =========================================================
# APPROVE CASE
# =========================================================


@pytest.mark.django_db
def test_approve_case_approves_segmentation_and_extraction(
    authenticated_client,
    reviewer,
    study,
):
    segmentation = SegmentationResult.objects.create(
        study=study,
        status=StatusChoices.COMPLETED,
    )

    extraction = ExtractionResult.objects.create(
        study=study,
        status=StatusChoices.COMPLETED,
        generated_report={"birads": "4C"},
    )

    response = authenticated_client.post(
        reverse(
            "approve-case",
            kwargs={"study_id": study.orthanc_path},
        ),
        {
            "mask": "confirmed",
            "report": {"zmiany": [{"birads": "4C"}]},
            "fields": {"zmiany.0.birads": "confirmed"},
        },
        format="json",
    )

    segmentation.refresh_from_db()
    extraction.refresh_from_db()

    assert response.status_code == status.HTTP_200_OK
    assert segmentation.status == StatusChoices.APPROVED
    assert segmentation.accepted_by == reviewer
    assert segmentation.accepted_at == timezone.now().date()
    assert extraction.status == StatusChoices.APPROVED
    assert extraction.accepted_by == reviewer
    assert extraction.accepted_at == timezone.now().date()
    assert extraction.accepted_report == {"zmiany": [{"birads": "4C"}]}
    assert extraction.field_checks == {"zmiany.0.birads": "confirmed"}


@pytest.mark.django_db
def test_approve_case_marks_segmentation_as_corrected(
    authenticated_client,
    study,
):
    segmentation = SegmentationResult.objects.create(
        study=study,
        status=StatusChoices.COMPLETED,
    )

    response = authenticated_client.post(
        reverse(
            "approve-case",
            kwargs={"study_id": study.orthanc_path},
        ),
        {"mask": "corrected"},
        format="json",
    )

    segmentation.refresh_from_db()
    assert response.status_code == status.HTTP_200_OK
    assert segmentation.status == StatusChoices.CORRECTED


@pytest.mark.django_db
def test_approve_case_marks_extraction_as_corrected_when_field_changed(
    authenticated_client,
    study,
):
    SegmentationResult.objects.create(study=study, status=StatusChoices.COMPLETED)
    extraction = ExtractionResult.objects.create(
        study=study,
        status=StatusChoices.COMPLETED,
    )

    response = authenticated_client.post(
        reverse(
            "approve-case",
            kwargs={"study_id": study.orthanc_path},
        ),
        {
            "report": {"zmiany": [{"birads": "5"}]},
            "fields": {"zmiany.0.birads": "corrected"},
        },
        format="json",
    )

    extraction.refresh_from_db()
    assert response.status_code == status.HTTP_200_OK
    assert extraction.status == StatusChoices.CORRECTED
    assert extraction.accepted_report == {"zmiany": [{"birads": "5"}]}


@pytest.mark.django_db
def test_approve_case_refuses_a_case_whose_mask_is_not_ready_and_saves_nothing(
    authenticated_client,
    study,
):
    segmentation = SegmentationResult.objects.create(
        study=study,
        status=StatusChoices.PENDING,
    )
    # the form alone could be approved; the whole case is refused, so it stays as it was
    extraction = ExtractionResult.objects.create(
        study=study,
        status=StatusChoices.COMPLETED,
    )

    response = authenticated_client.post(
        reverse(
            "approve-case",
            kwargs={"study_id": study.orthanc_path},
        ),
        {},
        format="json",
    )

    segmentation.refresh_from_db()
    extraction.refresh_from_db()
    assert response.status_code == status.HTTP_409_CONFLICT
    assert response.json()["code"] == "not_approvable"
    assert segmentation.status == StatusChoices.PENDING
    assert extraction.status == StatusChoices.COMPLETED
    assert not AuditLog.objects.exists()


@pytest.mark.django_db
def test_approve_case_refuses_a_case_without_a_mask(authenticated_client, study):
    ExtractionResult.objects.create(study=study, status=StatusChoices.COMPLETED)

    response = authenticated_client.post(
        reverse("approve-case", kwargs={"study_id": study.orthanc_path}), {}, format="json"
    )

    assert response.status_code == status.HTTP_409_CONFLICT


@pytest.mark.django_db
def test_approve_case_keeps_a_mask_approved_before_and_approves_the_form(
    authenticated_client,
    reviewer,
    study,
):
    # the usual order: the mask is approved on its own, the case follows with the form
    approved_at = timezone.now().date()
    segmentation = SegmentationResult.objects.create(
        study=study,
        status=StatusChoices.CORRECTED,
        accepted_by=reviewer,
        accepted_at=approved_at,
    )
    extraction = ExtractionResult.objects.create(study=study, status=StatusChoices.COMPLETED)

    response = authenticated_client.post(
        reverse("approve-case", kwargs={"study_id": study.orthanc_path}),
        {"mask": "confirmed"},
        format="json",
    )

    segmentation.refresh_from_db()
    extraction.refresh_from_db()
    assert response.status_code == status.HTTP_200_OK
    assert segmentation.status == StatusChoices.CORRECTED
    assert extraction.status == StatusChoices.APPROVED
    assert list(AuditLog.objects.values_list("kind", flat=True)) == ["form_approved"]


@pytest.mark.django_db
def test_approve_case_returns_404_for_unknown_study(
    authenticated_client,
):
    response = authenticated_client.post(
        reverse(
            "approve-case",
            kwargs={"study_id": "unknown-study"},
        ),
        {},
        format="json",
    )
    assert response.status_code == status.HTTP_404_NOT_FOUND


# =========================================================
# APPROVE MASK
# =========================================================


@pytest.mark.django_db
def test_approve_mask_approves_segmentation(
    authenticated_client,
    reviewer,
    study,
):
    segmentation = SegmentationResult.objects.create(
        study=study,
        status=StatusChoices.COMPLETED,
    )

    response = authenticated_client.post(
        reverse(
            "approve-mask",
            kwargs={"study_id": study.orthanc_path},
        ),
        {"mask": "confirmed"},
        format="json",
    )

    segmentation.refresh_from_db()
    assert response.status_code == status.HTTP_200_OK
    assert segmentation.status == StatusChoices.APPROVED
    assert segmentation.accepted_by == reviewer
    assert segmentation.accepted_at == timezone.now().date()


@pytest.mark.django_db
def test_approve_mask_marks_segmentation_as_corrected(
    authenticated_client,
    study,
):
    segmentation = SegmentationResult.objects.create(
        study=study,
        status=StatusChoices.COMPLETED,
    )

    response = authenticated_client.post(
        reverse(
            "approve-mask",
            kwargs={"study_id": study.orthanc_path},
        ),
        {"mask": "corrected"},
        format="json",
    )

    segmentation.refresh_from_db()
    assert response.status_code == status.HTTP_200_OK
    assert segmentation.status == StatusChoices.CORRECTED


@pytest.mark.django_db
def test_approve_mask_refuses_a_pending_segmentation(
    authenticated_client,
    study,
):
    segmentation = SegmentationResult.objects.create(
        study=study,
        status=StatusChoices.PENDING,
    )

    response = authenticated_client.post(
        reverse(
            "approve-mask",
            kwargs={"study_id": study.orthanc_path},
        ),
        {},
        format="json",
    )

    segmentation.refresh_from_db()
    assert response.status_code == status.HTTP_409_CONFLICT
    assert segmentation.status == StatusChoices.PENDING


# =========================================================
# REOPEN CASE
# =========================================================


@pytest.mark.django_db
def test_reopen_case_reopens_approved_results(
    authenticated_client,
    study,
):
    segmentation = SegmentationResult.objects.create(
        study=study,
        status=StatusChoices.APPROVED,
    )
    extraction = ExtractionResult.objects.create(
        study=study,
        status=StatusChoices.CORRECTED,
    )

    response = authenticated_client.post(
        reverse(
            "reopen-case",
            kwargs={"study_id": study.orthanc_path},
        )
    )

    segmentation.refresh_from_db()
    extraction.refresh_from_db()
    assert response.status_code == status.HTTP_200_OK
    assert segmentation.status == StatusChoices.COMPLETED
    assert extraction.status == StatusChoices.COMPLETED
    assert segmentation.accepted_by is None
    assert extraction.accepted_by is None
    assert segmentation.accepted_at is None
    assert extraction.accepted_at is None


@pytest.mark.django_db
def test_reopen_case_does_not_change_unapproved_results(
    authenticated_client,
    study,
):
    segmentation = SegmentationResult.objects.create(
        study=study,
        status=StatusChoices.PENDING,
    )
    extraction = ExtractionResult.objects.create(
        study=study,
        status=StatusChoices.PROCESSING,
    )

    response = authenticated_client.post(
        reverse(
            "reopen-case",
            kwargs={"study_id": study.orthanc_path},
        )
    )

    segmentation.refresh_from_db()
    extraction.refresh_from_db()
    assert response.status_code == status.HTTP_200_OK
    assert segmentation.status == StatusChoices.PENDING
    assert extraction.status == StatusChoices.PROCESSING


# =========================================================
# UNAPPROVE MASK
# =========================================================


@pytest.mark.django_db
def test_unapprove_mask_changes_approved_to_completed(
    authenticated_client,
    study,
):
    segmentation = SegmentationResult.objects.create(
        study=study,
        status=StatusChoices.APPROVED,
    )

    response = authenticated_client.post(
        reverse(
            "unapprove-mask",
            kwargs={"study_id": study.orthanc_path},
        )
    )

    segmentation.refresh_from_db()
    assert response.status_code == status.HTTP_200_OK
    assert segmentation.status == StatusChoices.COMPLETED
    assert segmentation.accepted_by is None
    assert segmentation.accepted_at is None


@pytest.mark.django_db
def test_unapprove_mask_changes_corrected_to_completed(
    authenticated_client,
    study,
):
    segmentation = SegmentationResult.objects.create(
        study=study,
        status=StatusChoices.CORRECTED,
    )

    response = authenticated_client.post(
        reverse(
            "unapprove-mask",
            kwargs={"study_id": study.orthanc_path},
        )
    )

    segmentation.refresh_from_db()
    assert response.status_code == status.HTTP_200_OK
    assert segmentation.status == StatusChoices.COMPLETED


@pytest.mark.django_db
def test_unapprove_mask_does_not_change_pending_segmentation(
    authenticated_client,
    study,
):
    segmentation = SegmentationResult.objects.create(
        study=study,
        status=StatusChoices.PENDING,
    )

    response = authenticated_client.post(
        reverse(
            "unapprove-mask",
            kwargs={"study_id": study.orthanc_path},
        )
    )

    segmentation.refresh_from_db()
    assert response.status_code == status.HTTP_200_OK
    assert segmentation.status == StatusChoices.PENDING


# =========================================================
# APPROVE FORM
# =========================================================


@pytest.mark.django_db
def test_approve_form_approves_extraction(
    authenticated_client,
    reviewer,
    study,
):
    extraction = ExtractionResult.objects.create(
        study=study,
        status=StatusChoices.COMPLETED,
    )

    response = authenticated_client.post(
        reverse(
            "approve-form",
            kwargs={"study_id": study.orthanc_path},
        ),
        {
            "report": {"zmiany": [{"birads": "4C"}]},
            "fields": {
                "zmiany.0.birads": "confirmed",
                "zmiany.0.obserwacje.0.wymiary": "confirmed",
            },
        },
        format="json",
    )

    extraction.refresh_from_db()
    assert response.status_code == status.HTTP_200_OK
    assert extraction.status == StatusChoices.APPROVED
    assert extraction.accepted_by == reviewer
    assert extraction.accepted_report == {"zmiany": [{"birads": "4C"}]}
    assert extraction.field_checks["zmiany.0.obserwacje.0.wymiary"] == "confirmed"


@pytest.mark.django_db
def test_approve_form_marks_extraction_as_corrected(
    authenticated_client,
    study,
):
    extraction = ExtractionResult.objects.create(
        study=study,
        status=StatusChoices.COMPLETED,
    )

    response = authenticated_client.post(
        reverse(
            "approve-form",
            kwargs={"study_id": study.orthanc_path},
        ),
        {
            "report": {"zmiany": [{"birads": "5"}]},
            "fields": {"zmiany.0.birads": "corrected"},
        },
        format="json",
    )

    extraction.refresh_from_db()
    assert response.status_code == status.HTTP_200_OK
    assert extraction.status == StatusChoices.CORRECTED


@pytest.mark.django_db
def test_approve_form_stores_field_checks(
    authenticated_client,
    study,
):
    extraction = ExtractionResult.objects.create(
        study=study,
        status=StatusChoices.COMPLETED,
    )

    response = authenticated_client.post(
        reverse(
            "approve-form",
            kwargs={"study_id": study.orthanc_path},
        ),
        {
            "report": {"zmiany": [{"birads": "4C"}]},
            "fields": {"zmiany.0.birads": "confirmed", "wniosek.zalecenie": "unverified"},
        },
        format="json",
    )

    extraction.refresh_from_db()
    assert response.status_code == status.HTTP_200_OK
    assert extraction.status == StatusChoices.APPROVED
    assert extraction.field_checks == {
        "zmiany.0.birads": "confirmed",
        "wniosek.zalecenie": "unverified",
    }


@pytest.mark.django_db
def test_approve_form_marks_corrected_from_field_checks(
    authenticated_client,
    study,
):
    extraction = ExtractionResult.objects.create(
        study=study,
        status=StatusChoices.COMPLETED,
    )

    response = authenticated_client.post(
        reverse(
            "approve-form",
            kwargs={"study_id": study.orthanc_path},
        ),
        {
            "report": {"zmiany": [{"birads": "4C"}]},
            "fields": {"zmiany.0.birads": "confirmed", "wezly.0.uwagi": "corrected"},
        },
        format="json",
    )

    extraction.refresh_from_db()
    assert response.status_code == status.HTTP_200_OK
    assert extraction.status == StatusChoices.CORRECTED


@pytest.mark.django_db
def test_approve_form_again_replaces_the_answers(
    authenticated_client,
    study,
):
    extraction = ExtractionResult.objects.create(
        study=study,
        status=StatusChoices.APPROVED,
        accepted_report={"zmiany": [{"birads": "4C"}]},
        field_checks={"zmiany.0.birads": "confirmed"},
    )

    response = authenticated_client.post(
        reverse(
            "approve-form",
            kwargs={"study_id": study.orthanc_path},
        ),
        {
            "report": {"zmiany": [{"birads": "5"}]},
            "fields": {"zmiany.0.birads": "corrected"},
        },
        format="json",
    )

    extraction.refresh_from_db()
    assert response.status_code == status.HTTP_200_OK
    assert extraction.status == StatusChoices.CORRECTED
    assert extraction.accepted_report == {"zmiany": [{"birads": "5"}]}
    assert extraction.field_checks == {"zmiany.0.birads": "corrected"}


@pytest.mark.django_db
def test_approve_form_does_not_change_pending_extraction(
    authenticated_client,
    study,
):
    extraction = ExtractionResult.objects.create(
        study=study,
        status=StatusChoices.PENDING,
    )

    response = authenticated_client.post(
        reverse(
            "approve-form",
            kwargs={"study_id": study.orthanc_path},
        ),
        {"report": {"zmiany": [{"birads": "4C"}]}},
        format="json",
    )

    extraction.refresh_from_db()
    assert response.status_code == status.HTTP_200_OK
    assert extraction.status == StatusChoices.PENDING
    assert extraction.accepted_report is None


# =========================================================
# UNAPPROVE FORM
# =========================================================


@pytest.mark.django_db
def test_unapprove_form_changes_approved_to_completed(
    authenticated_client,
    study,
):
    extraction = ExtractionResult.objects.create(
        study=study,
        status=StatusChoices.APPROVED,
        accepted_report={"birads": "4C"},
    )

    response = authenticated_client.post(
        reverse(
            "unapprove-form",
            kwargs={"study_id": study.orthanc_path},
        )
    )

    extraction.refresh_from_db()
    assert response.status_code == status.HTTP_200_OK
    assert extraction.status == StatusChoices.COMPLETED
    assert extraction.accepted_by is None
    assert extraction.accepted_at is None


@pytest.mark.django_db
def test_unapprove_form_changes_corrected_to_completed(
    authenticated_client,
    study,
):
    extraction = ExtractionResult.objects.create(
        study=study,
        status=StatusChoices.CORRECTED,
    )

    response = authenticated_client.post(
        reverse(
            "unapprove-form",
            kwargs={"study_id": study.orthanc_path},
        )
    )

    extraction.refresh_from_db()
    assert response.status_code == status.HTTP_200_OK
    assert extraction.status == StatusChoices.COMPLETED


@pytest.mark.django_db
def test_unapprove_form_does_not_change_pending_extraction(
    authenticated_client,
    study,
):
    extraction = ExtractionResult.objects.create(
        study=study,
        status=StatusChoices.PENDING,
    )

    response = authenticated_client.post(
        reverse(
            "unapprove-form",
            kwargs={"study_id": study.orthanc_path},
        )
    )

    extraction.refresh_from_db()
    assert response.status_code == status.HTTP_200_OK
    assert extraction.status == StatusChoices.PENDING


@pytest.mark.django_db
def test_approve_form_ignores_the_old_per_lesion_answers(
    authenticated_client,
    study,
):
    extraction = ExtractionResult.objects.create(
        study=study,
        status=StatusChoices.COMPLETED,
    )

    response = authenticated_client.post(
        reverse(
            "approve-form",
            kwargs={"study_id": study.orthanc_path},
        ),
        {
            "report": {"zmiany": [{"birads": "5"}]},
            "lesions": {"0": {"birads": {"value": "5", "state": "corrected"}}},
            "fields": {"zmiany.0.birads": "confirmed"},
        },
        format="json",
    )

    extraction.refresh_from_db()
    assert response.status_code == status.HTTP_200_OK
    assert extraction.status == StatusChoices.APPROVED


@pytest.mark.django_db
def test_approve_form_again_without_a_report_keeps_the_corrected_status(
    authenticated_client,
    study,
):
    extraction = ExtractionResult.objects.create(
        study=study,
        status=StatusChoices.CORRECTED,
        accepted_report={"zmiany": [{"birads": "5"}]},
        field_checks={"zmiany.0.birads": "corrected"},
    )

    response = authenticated_client.post(
        reverse(
            "approve-form",
            kwargs={"study_id": study.orthanc_path},
        ),
        {},
        format="json",
    )

    extraction.refresh_from_db()
    assert response.status_code == status.HTTP_200_OK
    assert extraction.status == StatusChoices.CORRECTED
    assert extraction.accepted_report == {"zmiany": [{"birads": "5"}]}
    assert extraction.field_checks == {"zmiany.0.birads": "corrected"}


@pytest.mark.django_db
def test_approve_form_with_a_new_report_without_corrections_clears_the_corrected_status(
    authenticated_client,
    study,
):
    extraction = ExtractionResult.objects.create(
        study=study,
        status=StatusChoices.CORRECTED,
        accepted_report={"zmiany": [{"birads": "5"}]},
        field_checks={"zmiany.0.birads": "corrected"},
    )

    response = authenticated_client.post(
        reverse(
            "approve-form",
            kwargs={"study_id": study.orthanc_path},
        ),
        {"report": {"zmiany": [{"birads": "4C"}]}, "fields": {"zmiany.0.birads": "confirmed"}},
        format="json",
    )

    extraction.refresh_from_db()
    assert response.status_code == status.HTTP_200_OK
    assert extraction.status == StatusChoices.APPROVED
