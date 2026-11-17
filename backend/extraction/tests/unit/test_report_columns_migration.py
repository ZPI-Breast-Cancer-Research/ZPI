"""mlops 0005 creates the first OCR version; extraction 0012/0013 move ``result`` and
``provenance`` into the report columns and drop them."""

import pytest
from django.db import connection
from django.db.migrations.executor import MigrationExecutor

BEFORE = [("extraction", "0011_report_processing"), ("mlops", "0004_remove_replaced_fields")]
AFTER = [("extraction", "0013_remove_result_and_provenance")]


def _migrate(targets):
    executor = MigrationExecutor(connection)
    executor.loader.build_graph()
    executor.migrate(targets)
    return executor.loader.project_state(targets).apps


@pytest.mark.django_db(transaction=True)
def test_the_json_result_moves_to_columns_and_scans_point_at_the_first_ocr_version():
    # Arrange
    apps = _migrate(BEFORE)
    # going back leaves the version created by the test database setup; start without one
    apps.get_model("mlops", "ModelVersion").objects.filter(module="ocr").delete()
    Report = apps.get_model("extraction", "ExtractionResult")
    provenance = {
        "ocr_engine": "paddle",
        "ocr_engine_version": "3.1",
        "ocr_mean_confidence": 0.9,
        "page_rotations": [0, 180],
        "schema_version": "3",
    }
    scan = Report.objects.create(
        status="COMPLETED",
        provenance=provenance,
        result={
            "text": "Opis",
            "ocr_seconds": 2.0,
            "llm_seconds": 5.0,
            "attempts": 2,
            "provenance": provenance,
        },
    )
    failed_ocr = Report.objects.create(
        status="FAILED", error="OCR: unreadable", result={"text": "", "provenance": {}}
    )
    failed_llm = Report.objects.create(
        status="FAILED", error="LLM: down", result={"text": "Opis", "provenance": {}}
    )
    untouched = Report.objects.create(status="UPLOADED")

    # Act
    apps = _migrate(AFTER)

    # Assert
    Report = apps.get_model("extraction", "ExtractionResult")
    ocr = apps.get_model("mlops", "ModelVersion").objects.get(module="ocr")
    assert (ocr.status, ocr.ocr_engine) == ("production", "paddle")
    assert ocr.periods.filter(ended_at__isnull=True).exists()

    scan = Report.objects.get(pk=scan.pk)
    assert scan.ocr_model_id == ocr.id
    assert (scan.ocr_text, scan.ocr_confidence, scan.ocr_engine_version) == ("Opis", 0.9, "3.1")
    assert (scan.ocr_seconds, scan.llm_seconds, scan.attempts) == (2.0, 5.0, 2)
    assert (scan.page_rotations, scan.schema_version) == ([0, 180], "3")
    assert Report.objects.get(pk=failed_ocr.pk).failed_step == "ocr"
    assert Report.objects.get(pk=failed_llm.pk).failed_step == "llm"
    assert Report.objects.get(pk=untouched.pk).ocr_text == ""
