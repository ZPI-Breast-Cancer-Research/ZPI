"""`manage.py save_ocr_metrics` stores the OCR metrics of an evaluation report in the version."""

import json

import pytest
from django.core.management import CommandError, call_command
from mlops.models import ModelVersion

SCORES = {
    "ocr_metrics": {
        "cer": 0.04,
        "word_error": 0.02,
        "worst_cer": 0.11,
        "mean_confidence": 0.93,
        "seconds_per_page": 1.8,
        "cases": 12,
    }
}


@pytest.fixture
def ocr(db):
    return ModelVersion.objects.create(module="ocr", name="ocr", version="ocr-test", status="new")


def _report(tmp_path, scores=SCORES):
    path = tmp_path / "scores.json"
    path.write_text(json.dumps(scores), encoding="utf-8")
    return path


def test_the_metrics_land_in_the_version(tmp_path, ocr):
    call_command("save_ocr_metrics", "ocr-test", _report(tmp_path), dataset="gold-v2")

    ocr.refresh_from_db()
    assert ocr.metrics == {
        "cer": 0.04,
        "word_error": 0.02,
        "worst_cer": 0.11,
        "mean_confidence": 0.93,
        "seconds_per_page": 1.8,
    }
    assert (ocr.metrics_cases, ocr.dataset) == (12, "gold-v2")


def test_a_proposed_version_keeps_its_metrics(tmp_path, ocr):
    ocr.status = "candidate"
    ocr.save()

    with pytest.raises(CommandError):
        call_command("save_ocr_metrics", "ocr-test", _report(tmp_path), dataset="gold-v2")


def test_a_report_without_ocr_documents_is_refused(tmp_path, ocr):
    empty = {"ocr_metrics": {**SCORES["ocr_metrics"], "cases": 0}}

    with pytest.raises(CommandError):
        call_command("save_ocr_metrics", "ocr-test", _report(tmp_path, empty), dataset="x")
