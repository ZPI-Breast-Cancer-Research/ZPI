"""The OCR metrics an evaluation run gives an OCR version (docs/database.md)."""

import pytest

from workers.extraction.evaluation.scores import OCRScore


def test_the_metrics_of_an_ocr_version():
    score = OCRScore()
    score.add("a", "abcd", "abcd", confidence=0.9, seconds=4.0, pages=2)
    score.add("b", "abcd", "abcx", confidence=0.7, seconds=1.0, pages=1)

    metrics = score.metrics()

    assert metrics["cer"] == pytest.approx(0.125)
    assert metrics["worst_cer"] == pytest.approx(0.25)
    assert metrics["word_error"] == pytest.approx(0.5)
    assert metrics["mean_confidence"] == pytest.approx(0.8)
    assert metrics["seconds_per_page"] == pytest.approx(1.5)


def test_without_documents_every_metric_is_empty():
    assert set(OCRScore().metrics().values()) == {None}
