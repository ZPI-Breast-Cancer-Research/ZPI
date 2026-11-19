import json
from pathlib import Path

import pytest

from workers.extraction.config import Settings
from workers.extraction.evaluation import tracking
from workers.extraction.evaluation.report import Report
from workers.extraction.tests.factories import provenance, result


@pytest.fixture(autouse=True)
def no_git(monkeypatch):
    monkeypatch.setattr(tracking, "git_state", lambda: {"git_commit": "abc123", "git_dirty": False})


def record(results, settings=None, gold_dir=None):
    return tracking.build_record(
        "001",
        "test",
        hypothesis="h",
        settings=settings or Settings(),
        results=results,
        report=Report(evaluated=[r.source for r in results]),
        gold_dir=gold_dir or Path("nie-ma"),
        predictions=Path("runs/001_test.jsonl"),
    )


@pytest.mark.parametrize(
    ("name", "expected"),
    [("Baseline OCR", "baseline-ocr"), ("few_shot=0!", "few-shot-0"), ("!!!", "run")],
)
def test_slugify(name, expected):
    # Act / Assert
    assert tracking.slugify(name) == expected


def test_config_comes_from_what_produced_the_results():
    # Arrange: the results were made with settings that differ from the current ones.
    results = [result(provenance=provenance(few_shot=0, structured_output=False))]
    settings = Settings(few_shot_examples=1, llm_structured_output=True)

    # Act
    rec = record(results, settings)

    # Assert
    assert rec["config"]["few_shot"] == 0
    assert rec["config"]["structured_output"] is False
    assert rec["config"]["llm_model"] == "fake-model"


def test_config_falls_back_to_settings_without_results():
    # Arrange
    settings = Settings(few_shot_examples=2, llm_structured_output=False, llm_model="m")

    # Act
    rec = record([], settings)

    # Assert
    assert rec["config"]["few_shot"] == 2
    assert rec["config"]["structured_output"] is False
    assert rec["config"]["llm_model"] == "m"


def test_input_is_scans_when_any_result_went_through_ocr():
    # Arrange
    results = [result(provenance=provenance(ocr_engine="fake-ocr"))]

    # Act / Assert
    assert record(results)["input"] == "scans"
    assert record([result()])["input"] == "transcripts"


def test_runtime_counts_failures_and_mean_times():
    # Arrange
    results = [result(llm_seconds=2.0), result(llm_seconds=4.0), result(status="error", data=None)]

    # Act
    runtime = record(results)["runtime"]

    # Assert
    assert runtime["failed"] == 1
    assert runtime["llm_seconds_mean"] == pytest.approx(7 / 3, abs=0.01)


def test_record_contains_no_report_text():
    # Arrange
    results = [result(text="Opis badania: TAJNY-TEKST-RAPORTU")]

    # Act
    rec = record(results)

    # Assert
    assert "TAJNY-TEKST-RAPORTU" not in json.dumps(rec, ensure_ascii=False)


def test_gold_sha_changes_when_a_gold_file_changes(tmp_path):
    # Arrange
    (tmp_path / "text").mkdir()
    (tmp_path / "a.json").write_text("{}")
    (tmp_path / "text" / "a.txt").write_text("tekst")
    before = tracking.gold_sha(tmp_path)

    # Act
    (tmp_path / "text" / "a.txt").write_text("tekst zmieniony")

    # Assert
    assert tracking.gold_sha(tmp_path) != before
