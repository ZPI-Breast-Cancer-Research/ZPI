"""The Celery task ``extraction.run`` with the backend database: statuses, the result in the
report columns, the versions in use.

MinIO and the LLM are replaced (``download_file`` writes a synthetic report, ``FakeLLM`` answers);
the database is the real one from the Django test settings.
"""

import pytest
from django.conf import settings

if not settings.configured:  # e.g. pytest -p no:django: the rest of the suite runs without it
    pytest.skip("needs Django settings and a database", allow_module_level=True)

from extraction.models import ExtractionResult as ExtractionRow  # noqa: E402
from extraction.models import SourceChoices, StatusChoices  # noqa: E402
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
    monkeypatch.setattr(tasks, "_extractor", lambda ocr: Extractor(llm))
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
    row = ExtractionRow.objects.create(report_path=KEY, status=StatusChoices.PENDING)

    # Act
    tasks.run(keys=[KEY], extraction_id=row.id)

    # Assert
    row.refresh_from_db()
    assert storage == [("reports", KEY)]
    assert row.status == StatusChoices.COMPLETED
    assert row.generated_report == extraction().model_dump(mode="json")
    assert row.model == model
    assert row.warnings == []
    assert row.error == row.failed_step == ""


def test_the_result_goes_to_the_columns_of_its_step(monkeypatch, storage):
    # Arrange: review/views.py builds what the frontend reads from these columns
    use_llm(monkeypatch, answer_json())
    row = ExtractionRow.objects.create(report_path=KEY, status=StatusChoices.PENDING)

    # Act
    returned = tasks.run(keys=[KEY], extraction_id=row.id)

    # Assert
    row.refresh_from_db()
    assert row.ocr_text == returned["text"] != ""
    assert row.generated_report == returned["data"]
    assert row.attempts == returned["attempts"] == 1
    assert row.llm_seconds == returned["llm_seconds"]
    assert row.schema_version == returned["provenance"]["schema_version"]
    # a text report: no OCR step
    assert row.ocr_seconds is None
    assert row.page_rotations == []


def test_a_scan_points_at_the_ocr_version_in_use_and_a_text_does_not(monkeypatch, storage):
    # Arrange: the first OCR version comes from the migration (mlops 0005)
    use_llm(monkeypatch, answer_json(), answer_json())
    ocr, _ = ModelVersion.objects.get_or_create(
        module="ocr",
        status=ModelVersion.StatusChoices.PRODUCTION,
        defaults={"name": "ocr", "version": "1", "ocr_engine": "paddle"},
    )
    scan = ExtractionRow.objects.create(
        report_path=KEY, source=SourceChoices.SCAN, status=StatusChoices.PENDING
    )
    text = ExtractionRow.objects.create(
        report_path=KEY, source=SourceChoices.TEXT, status=StatusChoices.PENDING
    )
    seen = []
    monkeypatch.setattr(
        tasks,
        "_extractor",
        lambda version: seen.append(version) or Extractor(FakeLLM([answer_json()])),
    )

    # Act
    tasks.run(keys=[KEY], extraction_id=scan.id)
    tasks.run(keys=[KEY], extraction_id=text.id)

    # Assert
    scan.refresh_from_db()
    text.refresh_from_db()
    assert scan.ocr_model == ocr
    assert text.ocr_model is None
    assert seen == [ocr, ocr]  # the extractor is set up from the OCR version in use


def test_the_extractor_reads_pages_the_way_the_ocr_version_says(monkeypatch):
    # Arrange
    created = {}

    def from_settings(settings, *, ocr_options=None, log=None):
        created.update(engine=settings.ocr_engine, lang=settings.ocr_lang, options=ocr_options)
        return "extractor"

    monkeypatch.setattr(tasks.Extractor, "from_settings", from_settings)
    tasks._cached_extractor.cache_clear()
    version = ModelVersion(
        module="ocr",
        ocr_engine="paddle",
        ocr_settings={"lang": "en", "orientation": "none", "unwarp": True},
    )

    # Act
    extractor = tasks._extractor(version)

    # Assert
    assert extractor == "extractor"
    assert created == {"engine": "paddle", "lang": "en", "options": {"unwarp": True}}
    tasks._cached_extractor.cache_clear()


def test_generated_report_is_what_the_review_form_reads(monkeypatch, storage):
    # Arrange: review/views.py reads "zmiany" and "wniosek" at the top level of generated_report.
    from review.views import _as_fields

    use_llm(monkeypatch, answer_json())
    row = ExtractionRow.objects.create(report_path=KEY, status=StatusChoices.PENDING)

    # Act
    tasks.run(keys=[KEY], extraction_id=row.id)

    # Assert
    row.refresh_from_db()
    assert _as_fields(row.generated_report)["birads"] == "3"


def test_llm_error_is_saved_as_failed_with_the_reason(monkeypatch, storage):
    # Arrange
    use_llm(monkeypatch, LLMError("Cannot connect to http://localhost:1234/v1"))
    row = ExtractionRow.objects.create(report_path=KEY, status=StatusChoices.PENDING)

    # Act
    tasks.run(keys=[KEY], extraction_id=row.id)

    # Assert
    row.refresh_from_db()
    assert row.status == StatusChoices.FAILED
    assert row.error == "LLM: Cannot connect to http://localhost:1234/v1"
    assert row.generated_report is None
    assert row.failed_step == "llm"
    # the text OCR read stays, so the failure can be looked at
    assert row.ocr_text


def test_download_error_is_saved_as_failed(monkeypatch):
    # Arrange
    def download_file(bucket, key, path):
        raise OSError("MinIO unreachable")

    monkeypatch.setattr(tasks, "download_file", download_file)
    row = ExtractionRow.objects.create(report_path=KEY, status=StatusChoices.PENDING)

    # Act
    returned = tasks.run(keys=[KEY], extraction_id=row.id)

    # Assert
    row.refresh_from_db()
    assert row.status == StatusChoices.FAILED
    assert row.error == "OSError: MinIO unreachable"
    assert returned["status"] == "error"
    # failed before OCR: no step, no text
    assert (row.failed_step, row.ocr_text) == ("", "")


def test_retry_clears_the_previous_result(monkeypatch):
    # Arrange: a failed row with the result of its first attempt; the retry cannot even download
    def download_file(bucket, key, path):
        raise OSError("MinIO unreachable")

    monkeypatch.setattr(tasks, "download_file", download_file)
    row = ExtractionRow.objects.create(
        report_path=KEY,
        status=StatusChoices.FAILED,
        failed_step="llm",
        ocr_text="old",
        attempts=2,
    )

    # Act
    tasks.run(keys=[KEY], extraction_id=row.id)

    # Assert
    row.refresh_from_db()
    assert row.status == StatusChoices.FAILED
    assert (row.ocr_text, row.attempts, row.failed_step) == ("", 0, "")


def test_without_production_model_extraction_runs_and_model_stays_empty(monkeypatch, storage):
    # Arrange: only a candidate and a segmentation model exist.
    use_llm(monkeypatch, answer_json())
    production_model(status=ModelVersion.StatusChoices.CANDIDATE)
    production_model(module=ModelVersion.ModuleChoices.SEG)
    row = ExtractionRow.objects.create(report_path=KEY, status=StatusChoices.PENDING)

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
        # stored only: nobody ordered the processing (backend sets PENDING when it does)
        StatusChoices.UPLOADED,
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
    row = ExtractionRow.objects.create(report_path=KEY, status=StatusChoices.PENDING)

    class Watching(FakeLLM):
        def complete(self, messages, **kwargs):
            seen["status"] = ExtractionRow.objects.get(id=row.id).status
            return super().complete(messages, **kwargs)

    monkeypatch.setattr(tasks, "_extractor", lambda ocr: Extractor(Watching([answer_json()])))

    # Act
    tasks.run(keys=[KEY], extraction_id=row.id)

    # Assert
    assert seen["status"] == StatusChoices.PROCESSING


def test_uncertainty_is_saved_in_the_column_the_review_queue_sorts_by(monkeypatch, storage):
    # Arrange: an answer whose node quote is not in the report -> a heavy warning
    bad = extraction(wezly=[node(cytat="Węzeł nadobojczykowy lewy 25mm.")])
    use_llm(monkeypatch, answer_json(bad))
    row = ExtractionRow.objects.create(report_path=KEY, status=StatusChoices.PENDING)

    # Act
    tasks.run(keys=[KEY], extraction_id=row.id)

    # Assert
    row.refresh_from_db()
    assert 0 < row.uncertainty < 1
    assert row.warnings


def test_correct_extraction_of_a_text_report_has_zero_uncertainty(monkeypatch, storage):
    # Arrange
    use_llm(monkeypatch, answer_json())
    row = ExtractionRow.objects.create(report_path=KEY, status=StatusChoices.PENDING)

    # Act
    tasks.run(keys=[KEY], extraction_id=row.id)

    # Assert
    row.refresh_from_db()
    assert row.uncertainty == 0.0


def test_failed_extraction_has_maximum_uncertainty(monkeypatch, storage):
    # Arrange
    use_llm(monkeypatch, LLMError("down"))
    row = ExtractionRow.objects.create(report_path=KEY, status=StatusChoices.PENDING)

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
    row = ExtractionRow.objects.create(report_path=KEY, status=StatusChoices.PENDING)

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

    monkeypatch.setattr(tasks, "_extractor", lambda ocr: Extractor(Watching([answer_json()])))

    # Act
    tasks.run(keys=[KEY], extraction_id=row.id)

    # Assert
    row.refresh_from_db()
    assert seen["uncertainty"] is None
    assert row.uncertainty == 0.0
