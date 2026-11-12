"""The Celery task ``extraction.run`` with the backend database: statuses, saved result, model.

MinIO and the LLM are replaced (``download_file`` writes a synthetic report, ``FakeLLM`` answers);
the database is the real one from the Django test settings.
"""

import pytest
from django.conf import settings

if not settings.configured:  # e.g. pytest -p no:django: the rest of the suite runs without it
    pytest.skip("needs Django settings and a database", allow_module_level=True)

from extraction.models import ExtractionResult as ExtractionRow  # noqa: E402
from extraction.models import StatusChoices  # noqa: E402
from mlops.models import ModelVersion  # noqa: E402

from workers.extraction import tasks  # noqa: E402
from workers.extraction.errors import LLMError  # noqa: E402
from workers.extraction.pipeline import Extractor  # noqa: E402
from workers.extraction.tests.factories import (  # noqa: E402
    REPORT,
    FakeLLM,
    answer_json,
    extraction,
    node,
)

pytestmark = pytest.mark.django_db

KEY = "reports/abc/opis.txt"


@pytest.fixture
def storage(monkeypatch):
    """``download_file`` writes the synthetic report instead of reading MinIO."""
    downloaded = []

    def download_file(bucket, key, path):
        downloaded.append((bucket, key))
        path.write_text(REPORT, encoding="utf-8")
        return path

    monkeypatch.setattr(tasks, "download_file", download_file)
    return downloaded


def use_llm(monkeypatch, *answers):
    llm = FakeLLM(answers)
    monkeypatch.setattr(tasks, "_extractor", lambda: Extractor(llm))
    return llm


def production_model(**overrides):
    values = {
        "module": ModelVersion.ModuleChoices.EXT,
        "name": "extraction",
        "version": "1.0",
        "status": ModelVersion.StatusChoices.PRODUCTION,
    }
    return ModelVersion.objects.create(**{**values, **overrides})


def test_successful_extraction_is_saved_as_completed(monkeypatch, storage):
    # Arrange
    use_llm(monkeypatch, answer_json())
    model = production_model()
    row = ExtractionRow.objects.create(report_path=KEY)

    # Act
    tasks.run(keys=[KEY], extraction_id=row.id)

    # Assert
    row.refresh_from_db()
    assert storage == [("reports", KEY)]
    assert row.status == StatusChoices.COMPLETED
    assert row.generated_report == extraction().model_dump(mode="json")
    assert row.model == model
    assert row.warnings == []
    assert row.provenance["llm_model"] == "fake-model"
    assert row.error == ""


def test_full_result_with_the_ocr_text_is_saved_for_the_frontend(monkeypatch, storage):
    # Arrange: the frontend (review/extraction.ts) reads the whole ExtractionResult, text included
    use_llm(monkeypatch, answer_json())
    row = ExtractionRow.objects.create(report_path=KEY)

    # Act
    returned = tasks.run(keys=[KEY], extraction_id=row.id)

    # Assert
    row.refresh_from_db()
    assert row.result == returned
    assert row.result["status"] == "ok"
    assert row.result["text"]
    assert row.result["data"] == row.generated_report


def test_generated_report_is_what_the_review_form_reads(monkeypatch, storage):
    # Arrange: review/views.py reads "zmiany" and "wniosek" at the top level of generated_report.
    from review.views import _as_fields

    use_llm(monkeypatch, answer_json())
    row = ExtractionRow.objects.create(report_path=KEY)

    # Act
    tasks.run(keys=[KEY], extraction_id=row.id)

    # Assert
    row.refresh_from_db()
    assert _as_fields(row.generated_report)["birads"] == "3"


def test_llm_error_is_saved_as_failed_with_the_reason(monkeypatch, storage):
    # Arrange
    use_llm(monkeypatch, LLMError("Cannot connect to http://localhost:1234/v1"))
    row = ExtractionRow.objects.create(report_path=KEY)

    # Act
    tasks.run(keys=[KEY], extraction_id=row.id)

    # Assert
    row.refresh_from_db()
    assert row.status == StatusChoices.FAILED
    assert row.error == "LLM: Cannot connect to http://localhost:1234/v1"
    assert row.generated_report is None
    # the frontend shows a failed extraction from the result, with the text OCR read
    assert row.result["status"] == "error"
    assert row.result["error"] == row.error
    assert row.result["text"]


def test_download_error_is_saved_as_failed(monkeypatch):
    # Arrange
    def download_file(bucket, key, path):
        raise OSError("MinIO unreachable")

    monkeypatch.setattr(tasks, "download_file", download_file)
    row = ExtractionRow.objects.create(report_path=KEY)

    # Act
    returned = tasks.run(keys=[KEY], extraction_id=row.id)

    # Assert
    row.refresh_from_db()
    assert row.status == StatusChoices.FAILED
    assert row.error == "OSError: MinIO unreachable"
    assert returned["status"] == "error"
    assert row.result is None


def test_retry_clears_the_previous_result(monkeypatch):
    # Arrange: a failed row with the result of its first attempt; the retry cannot even download
    def download_file(bucket, key, path):
        raise OSError("MinIO unreachable")

    monkeypatch.setattr(tasks, "download_file", download_file)
    row = ExtractionRow.objects.create(
        report_path=KEY, status=StatusChoices.FAILED, result={"status": "error", "text": "old"}
    )

    # Act
    tasks.run(keys=[KEY], extraction_id=row.id)

    # Assert
    row.refresh_from_db()
    assert row.status == StatusChoices.FAILED
    assert row.result is None


def test_without_production_model_extraction_runs_and_model_stays_empty(monkeypatch, storage):
    # Arrange: only a candidate and a segmentation model exist.
    use_llm(monkeypatch, answer_json())
    production_model(status=ModelVersion.StatusChoices.CANDIDATE)
    production_model(module=ModelVersion.ModuleChoices.SEG)
    row = ExtractionRow.objects.create(report_path=KEY)

    # Act
    tasks.run(keys=[KEY], extraction_id=row.id)

    # Assert
    row.refresh_from_db()
    assert row.status == StatusChoices.COMPLETED
    assert row.model is None


@pytest.mark.parametrize(
    "status",
    [
        StatusChoices.APPROVED,
        StatusChoices.CORRECTED,
        StatusChoices.REJECTED,
        StatusChoices.COMPLETED,
    ],
)
def test_reviewed_or_finished_row_is_never_overwritten(monkeypatch, storage, status):
    # Arrange: a repeated or late task for a row that already has a result.
    llm = use_llm(monkeypatch, answer_json())
    row = ExtractionRow.objects.create(
        report_path=KEY, status=status, generated_report={"wniosek": {"birads": "4a"}}
    )

    # Act
    returned = tasks.run(keys=[KEY], extraction_id=row.id)

    # Assert
    row.refresh_from_db()
    assert returned["status"] == "skipped"
    assert row.status == status
    assert row.generated_report == {"wniosek": {"birads": "4a"}}
    assert llm.calls == []


@pytest.mark.parametrize("status", [StatusChoices.PROCESSING, StatusChoices.FAILED])
def test_retry_of_an_interrupted_or_failed_row_updates_the_same_row(monkeypatch, storage, status):
    # Arrange: the worker died mid-task (PROCESSING) or the previous attempt failed.
    use_llm(monkeypatch, answer_json())
    row = ExtractionRow.objects.create(report_path=KEY, status=status, error="earlier error")

    # Act
    tasks.run(keys=[KEY], extraction_id=row.id)

    # Assert
    row.refresh_from_db()
    assert ExtractionRow.objects.count() == 1
    assert row.status == StatusChoices.COMPLETED
    assert row.error == ""


def test_unknown_row_is_skipped_without_extracting(monkeypatch, storage):
    # Arrange
    llm = use_llm(monkeypatch, answer_json())

    # Act
    returned = tasks.run(keys=[KEY], extraction_id=999999)

    # Assert
    assert returned == {"status": "skipped", "extraction_id": 999999}
    assert llm.calls == []
    assert storage == []


def test_without_extraction_id_the_result_is_only_returned(monkeypatch, storage):
    # Arrange
    use_llm(monkeypatch, answer_json())

    # Act
    returned = tasks.run(keys=[KEY])

    # Assert
    assert returned["status"] == "ok"
    assert returned["source"] == "opis.txt"
    assert ExtractionRow.objects.count() == 0


def test_status_moves_to_processing_before_extraction(monkeypatch, storage):
    # Arrange: look at the row while the LLM is "working".
    seen = {}
    row = ExtractionRow.objects.create(report_path=KEY)

    class Watching(FakeLLM):
        def complete(self, messages, **kwargs):
            seen["status"] = ExtractionRow.objects.get(id=row.id).status
            return super().complete(messages, **kwargs)

    monkeypatch.setattr(tasks, "_extractor", lambda: Extractor(Watching([answer_json()])))

    # Act
    tasks.run(keys=[KEY], extraction_id=row.id)

    # Assert
    assert seen["status"] == StatusChoices.PROCESSING


def test_uncertainty_is_saved_in_the_column_the_review_queue_sorts_by(monkeypatch, storage):
    # Arrange: an answer whose node quote is not in the report -> a heavy warning
    bad = extraction(wezly=[node(cytat="Węzeł nadobojczykowy lewy 25mm.")])
    use_llm(monkeypatch, answer_json(bad))
    row = ExtractionRow.objects.create(report_path=KEY)

    # Act
    tasks.run(keys=[KEY], extraction_id=row.id)

    # Assert
    row.refresh_from_db()
    assert 0 < row.uncertainty < 1
    assert row.uncertainty == row.result["uncertainty"]
    assert row.result["uncertainty_components"]["warnings"] > 0


def test_correct_extraction_of_a_text_report_has_zero_uncertainty(monkeypatch, storage):
    # Arrange
    use_llm(monkeypatch, answer_json())
    row = ExtractionRow.objects.create(report_path=KEY)

    # Act
    tasks.run(keys=[KEY], extraction_id=row.id)

    # Assert
    row.refresh_from_db()
    assert row.uncertainty == 0.0


def test_failed_extraction_has_maximum_uncertainty(monkeypatch, storage):
    # Arrange
    use_llm(monkeypatch, LLMError("down"))
    row = ExtractionRow.objects.create(report_path=KEY)

    # Act
    tasks.run(keys=[KEY], extraction_id=row.id)

    # Assert
    row.refresh_from_db()
    assert row.uncertainty == 1.0


def test_failure_outside_the_pipeline_has_maximum_uncertainty(monkeypatch):
    # Arrange
    def download_file(bucket, key, path):
        raise OSError("MinIO unreachable")

    monkeypatch.setattr(tasks, "download_file", download_file)
    row = ExtractionRow.objects.create(report_path=KEY)

    # Act
    tasks.run(keys=[KEY], extraction_id=row.id)

    # Assert
    row.refresh_from_db()
    assert row.uncertainty == 1.0


def test_retry_clears_the_previous_uncertainty_while_it_runs(monkeypatch, storage):
    # Arrange: a failed row (uncertainty 1.0) retried; look at it while the LLM is "working"
    seen = {}
    row = ExtractionRow.objects.create(
        report_path=KEY, status=StatusChoices.FAILED, uncertainty=1.0
    )

    class Watching(FakeLLM):
        def complete(self, messages, **kwargs):
            seen["uncertainty"] = ExtractionRow.objects.get(id=row.id).uncertainty
            return super().complete(messages, **kwargs)

    monkeypatch.setattr(tasks, "_extractor", lambda: Extractor(Watching([answer_json()])))

    # Act
    tasks.run(keys=[KEY], extraction_id=row.id)

    # Assert
    row.refresh_from_db()
    assert seen["uncertainty"] is None
    assert row.uncertainty == 0.0
