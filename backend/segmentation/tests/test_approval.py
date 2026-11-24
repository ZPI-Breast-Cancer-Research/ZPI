"""segmentation/approval.py: the one way to approve a model mask and to take it back."""

import pytest
from django.contrib.auth import get_user_model
from django.utils import timezone
from patients.models import Study
from segmentation.approval import approve_mask, approve_mask_in_case, reopen_mask
from segmentation.errors import NotApprovable
from segmentation.models import SegmentationResult, StatusChoices

NOT_WAITING = [
    StatusChoices.PENDING,
    StatusChoices.PROCESSING,
    StatusChoices.FAILED,
    StatusChoices.REJECTED,
    StatusChoices.APPROVED,
    StatusChoices.CORRECTED,
]
RUNNING_OR_FAILED = [
    StatusChoices.PENDING,
    StatusChoices.PROCESSING,
    StatusChoices.FAILED,
    StatusChoices.REJECTED,
]
VERIFIED = [StatusChoices.APPROVED, StatusChoices.CORRECTED]


@pytest.fixture
def radiologist(db):
    return get_user_model().objects.create_user(
        username="radiologist", password="TestPassword123!", role="radiologist"
    )


@pytest.fixture
def make_result(db):
    def make(status, **fields):
        study = Study.objects.create(orthanc_path=f"study-{Study.objects.count()}")
        return SegmentationResult.objects.create(
            study=study, status=status, generated_path="1/study_1_model.nii.gz", **fields
        )

    return make


@pytest.fixture
def approved_result(make_result, radiologist):
    return make_result(
        StatusChoices.CORRECTED,
        accepted_by=radiologist,
        accepted_at=timezone.now().date(),
        accepted_path="1/study_1_corrected.nii.gz",
        approved_seg_series_uid="1.2.3",
        approved_seg_sop_uid="1.2.3.1",
    )


# --- approve_mask --------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("corrected", "status", "accepted_path"),
    [
        (False, StatusChoices.APPROVED, "1/study_1_model.nii.gz"),
        (True, StatusChoices.CORRECTED, None),
    ],
)
def test_approving_a_mask_waiting_for_review_records_who_and_when(
    make_result, radiologist, corrected, status, accepted_path
):
    # Arrange
    result = make_result(StatusChoices.COMPLETED)

    # Act
    approve_mask(result, radiologist, corrected=corrected)

    # Assert
    result.refresh_from_db()
    assert result.status == status
    assert result.accepted_by == radiologist
    assert result.accepted_at == timezone.now().date()
    assert result.accepted_path == accepted_path


@pytest.mark.parametrize("status", NOT_WAITING)
def test_a_mask_not_waiting_for_review_cannot_be_approved(make_result, radiologist, status):
    # Arrange
    result = make_result(status)

    # Act / Assert
    with pytest.raises(NotApprovable):
        approve_mask(result, radiologist, corrected=False)
    result.refresh_from_db()
    assert result.status == status
    assert result.accepted_by is None


def test_a_study_without_a_mask_cannot_be_approved(radiologist):
    with pytest.raises(NotApprovable):
        approve_mask(None, radiologist, corrected=False)


def test_not_approvable_is_answered_as_a_409_conflict():
    error = NotApprovable("result 1 is PROCESSING")

    assert error.status_code == 409
    assert error.payload()["code"] == "not_approvable"


# --- approve_mask_in_case ------------------------------------------------------------------------


def test_approving_the_case_approves_a_mask_waiting_for_review(make_result, radiologist):
    # Arrange
    result = make_result(StatusChoices.COMPLETED)

    # Act
    changed = approve_mask_in_case(result, radiologist, corrected=False)

    # Assert
    assert changed is True
    result.refresh_from_db()
    assert result.status == StatusChoices.APPROVED


@pytest.mark.parametrize("status", VERIFIED)
def test_approving_the_case_keeps_a_mask_approved_before(make_result, radiologist, status):
    # Arrange: the mask was approved on its own, the form comes later
    other = get_user_model().objects.create_user(username="other", password="TestPassword123!")
    result = make_result(status, accepted_by=other, accepted_at=timezone.now().date())

    # Act
    changed = approve_mask_in_case(result, radiologist, corrected=False)

    # Assert
    assert changed is False
    result.refresh_from_db()
    assert result.status == status
    assert result.accepted_by == other


@pytest.mark.parametrize("status", RUNNING_OR_FAILED)
def test_a_case_whose_mask_is_running_or_failed_cannot_be_approved(
    make_result, radiologist, status
):
    result = make_result(status)

    with pytest.raises(NotApprovable):
        approve_mask_in_case(result, radiologist, corrected=False)


def test_a_case_without_a_mask_cannot_be_approved(radiologist):
    with pytest.raises(NotApprovable):
        approve_mask_in_case(None, radiologist, corrected=False)


# --- reopen_mask ---------------------------------------------------------------------------------


def test_reopening_returns_the_mask_to_review_and_forgets_the_approved_seg(approved_result):
    # Act
    changed = reopen_mask(approved_result)

    # Assert
    assert changed is True
    approved_result.refresh_from_db()
    assert approved_result.status == StatusChoices.COMPLETED
    assert approved_result.accepted_by is None
    assert approved_result.accepted_at is None
    assert approved_result.accepted_path is None
    assert approved_result.approved_seg_series_uid == ""
    assert approved_result.approved_seg_sop_uid == ""
    assert approved_result.generated_path == "1/study_1_model.nii.gz"


@pytest.mark.parametrize("status", [StatusChoices.COMPLETED, *RUNNING_OR_FAILED])
def test_reopening_a_mask_that_is_not_approved_changes_nothing(make_result, status):
    # Arrange
    result = make_result(status)

    # Act
    changed = reopen_mask(result)

    # Assert
    assert changed is False
    result.refresh_from_db()
    assert result.status == status


def test_reopening_a_study_without_a_mask_changes_nothing():
    assert reopen_mask(None) is False


def test_a_reopened_mask_can_be_approved_again(approved_result, radiologist):
    # Act
    reopen_mask(approved_result)
    approve_mask(approved_result, radiologist, corrected=False)

    # Assert
    approved_result.refresh_from_db()
    assert approved_result.status == StatusChoices.APPROVED
    assert approved_result.accepted_by == radiologist
    assert approved_result.accepted_path == "1/study_1_model.nii.gz"
