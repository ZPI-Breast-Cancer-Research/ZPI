"""Gold and prediction files on disk -> evaluate -> report -> text table."""

import json

import pytest

from workers.extraction.errors import EvaluationDataError
from workers.extraction.evaluation import (
    FieldScore,
    evaluate,
    format_report,
    load_gold,
    load_predictions,
    load_transcripts,
)
from workers.extraction.schema import KategoriaBiRads, Wniosek
from workers.extraction.structuring.prompting import load_few_shot
from workers.extraction.tests.factories import (
    REPORT,
    error_result,
    extraction,
    provenance,
    result,
)

from .conftest import write_predictions


def run_eval(gold_dir, predictions_path, **kwargs):
    return evaluate(
        load_gold(gold_dir),
        load_predictions(predictions_path),
        transcripts=load_transcripts(gold_dir),
        **kwargs,
    )


def test_perfect_predictions_score_one(gold_dir, tmp_path):
    # Arrange
    path = write_predictions(tmp_path / "run.jsonl", [result("doc1.jpg"), result("doc2.jpg")])

    # Act
    report = run_eval(gold_dir, path)

    # Assert
    summary = report.summary()
    assert report.evaluated == ["doc1", "doc2"]
    assert summary["field_accuracy"] == 1.0
    assert summary["zmiany_f1"] == 1.0
    assert summary["wezly_f1"] == 1.0
    assert summary["wniosek_birads_accuracy"] == 1.0


def test_one_wrong_field_lowers_only_that_field(gold_dir, tmp_path):
    # Arrange
    wrong = extraction(
        wniosek=Wniosek(
            birads=KategoriaBiRads.K4,
            tekst="Zmiana w piersi prawej prawdopodobnie łagodna",
            zalecenie="kontrola za 6 miesięcy",
        )
    )
    path = write_predictions(
        tmp_path / "run.jsonl", [result("doc1.jpg", data=wrong), result("doc2.jpg")]
    )

    # Act
    report = run_eval(gold_dir, path)

    # Assert
    assert report.fields["wniosek.birads"] == FieldScore(correct=1, wrong=1)
    others = [s for name, s in report.fields.items() if name != "wniosek.birads"]
    assert all(s.wrong == s.missed == s.spurious == 0 for s in others)


def test_failed_prediction_is_scored_as_empty(gold_dir, tmp_path):
    # Arrange
    path = write_predictions(tmp_path / "run.jsonl", [error_result("doc1.jpg"), result("doc2.jpg")])

    # Act
    report = run_eval(gold_dir, path)

    # Assert
    assert report.errors == ["doc1"]
    assert report.evaluated == ["doc1", "doc2"]
    assert report.entities["zmiany"].gold == 2
    assert report.entities["zmiany"].matched == 1
    assert report.fields["wniosek.birads"] == FieldScore(correct=1, missed=1)


def test_missing_gold_or_prediction_is_skipped(gold_dir, tmp_path):
    # Arrange: doc2 has gold but no prediction, doc3 a prediction but no gold.
    path = write_predictions(tmp_path / "run.jsonl", [result("doc1.jpg"), result("doc3.jpg")])

    # Act
    report = run_eval(gold_dir, path)

    # Assert
    assert report.evaluated == ["doc1"]
    assert report.skipped == {"no_gold": ["doc3"], "no_prediction": ["doc2"]}


def test_few_shot_example_as_input_is_skipped_unless_included(gold_dir, tmp_path):
    # Arrange
    few_shot_report = load_few_shot()[0][0]
    path = write_predictions(
        tmp_path / "run.jsonl", [result("doc1.jpg", text=few_shot_report), result("doc2.jpg")]
    )

    # Act
    default = run_eval(gold_dir, path)
    included = run_eval(gold_dir, path, include_leaked=True)

    # Assert
    assert default.skipped == {"few_shot_leak": ["doc1"]}
    assert default.evaluated == ["doc2"]
    assert included.evaluated == ["doc1", "doc2"]


def test_cer_only_for_ocr_results_with_a_transcript(gold_dir, tmp_path):
    # Arrange: doc1 went through OCR and has a transcript; doc2 went through OCR, no transcript.
    ocr = provenance(ocr_engine="fake-ocr")
    ocr_text = REPORT.replace("hipoechogeniczna", "hipoechogenlczna")
    path = write_predictions(
        tmp_path / "run.jsonl",
        [result("doc1.jpg", text=ocr_text, provenance=ocr), result("doc2.jpg", provenance=ocr)],
    )

    # Act
    report = run_eval(gold_dir, path)

    # Assert
    assert list(report.ocr.documents) == ["doc1"]
    assert 0 < report.ocr.documents["doc1"] < 0.01


def test_transcript_run_has_no_cer(gold_dir, tmp_path):
    # Arrange: no OCR engine in provenance -> the LLM read a transcript.
    path = write_predictions(tmp_path / "run.jsonl", [result("doc1.jpg", text=REPORT)])

    # Act
    report = run_eval(gold_dir, path)

    # Assert
    assert report.ocr.documents == {}
    assert report.summary()["ocr_cer"] is None


def test_report_formats_and_exports(gold_dir, tmp_path):
    # Arrange
    path = write_predictions(tmp_path / "run.jsonl", [result("doc1.jpg"), error_result("doc2.jpg")])
    report = run_eval(gold_dir, path)

    # Act
    text = format_report(report)
    exported = json.loads(json.dumps(report.to_dict()))

    # Assert
    assert "model: fake-model | prompt: v6 | schema: 3" in text
    assert "documents: 2 evaluated (failed, scored as empty: doc2)" in text
    assert exported["errors"] == ["doc2"]
    assert exported["summary"]["zmiany_f1"] == pytest.approx(2 / 3)


def test_invalid_gold_file_names_the_file(gold_dir):
    # Arrange
    (gold_dir / "broken.json").write_text('{"source": "x"}', encoding="utf-8")

    # Act / Assert
    with pytest.raises(EvaluationDataError, match="broken.json"):
        load_gold(gold_dir)


def test_invalid_prediction_line_names_the_line(tmp_path):
    # Arrange
    path = tmp_path / "run.jsonl"
    path.write_text(result("doc1.jpg").model_dump_json() + "\n\n{zepsute}\n", encoding="utf-8")

    # Act / Assert
    with pytest.raises(EvaluationDataError, match="run.jsonl, line 3"):
        load_predictions(path)
