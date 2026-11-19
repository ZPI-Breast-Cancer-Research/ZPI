"""0005/0006 bring existing results to one mask per study with a FAILED status."""

import pytest
from django.db import connection
from django.db.migrations.executor import MigrationExecutor

BEFORE = [("segmentation", "0004_segmentationresult_measurements")]
AFTER = [("segmentation", "0006_one_result_per_study")]


def _migrate(targets):
    executor = MigrationExecutor(connection)
    executor.loader.build_graph()
    executor.migrate(targets)
    return executor.loader.project_state(targets).apps


@pytest.mark.django_db(transaction=True)
def test_duplicates_are_reduced_to_the_verified_or_newest_and_failures_marked():
    # Arrange
    apps = _migrate(BEFORE)
    Study = apps.get_model("patients", "Study")
    Result = apps.get_model("segmentation", "SegmentationResult")
    verified_study = Study.objects.create(orthanc_path="verified")
    approved = Result.objects.create(study=verified_study, status="APPROVED", generated_path="a")
    Result.objects.create(study=verified_study, status="COMPLETED", generated_path="b")
    plain_study = Study.objects.create(orthanc_path="plain")
    Result.objects.create(study=plain_study, status="COMPLETED", generated_path="c")
    newest = Result.objects.create(study=plain_study, status="REJECTED", generated_path=None)

    # Act
    apps = _migrate(AFTER)

    # Assert
    Result = apps.get_model("segmentation", "SegmentationResult")
    assert set(Result.objects.values_list("id", flat=True)) == {approved.id, newest.id}
    failed = Result.objects.get(id=newest.id)
    assert failed.status == "FAILED"
    assert failed.error
