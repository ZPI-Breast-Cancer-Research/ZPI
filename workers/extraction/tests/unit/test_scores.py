import pytest

from workers.extraction.evaluation.scores import EntityScore, FieldScore, OCRScore


def test_field_score_metrics():
    # Arrange
    score = FieldScore(correct=6, wrong=1, missed=2, spurious=1)

    # Act / Assert
    assert score.n == 10
    assert score.accuracy == pytest.approx(0.6)
    assert score.precision == pytest.approx(6 / 8)
    assert score.recall == pytest.approx(6 / 9)
    assert score.f1 == pytest.approx(2 * (6 / 8) * (6 / 9) / ((6 / 8) + (6 / 9)))


def test_empty_field_score_has_no_metrics():
    # Arrange
    score = FieldScore()

    # Act / Assert
    assert (score.accuracy, score.precision, score.recall, score.f1) == (None, None, None, None)


def test_field_score_with_nothing_correct_has_zero_f1():
    # Arrange
    score = FieldScore(wrong=2)

    # Act / Assert
    assert score.f1 == 0.0


def test_pooled_field_score_adds_counts():
    # Act
    total = FieldScore.pooled([FieldScore(1, 2, 3, 4), FieldScore(10, 20, 30, 40)])

    # Assert
    assert total == FieldScore(11, 22, 33, 44)


def test_entity_score_metrics():
    # Arrange
    score = EntityScore(gold=4, predicted=5, matched=3)

    # Act / Assert
    assert score.precision == pytest.approx(3 / 5)
    assert score.recall == pytest.approx(3 / 4)
    assert score.f1 == pytest.approx(2 * 0.6 * 0.75 / (0.6 + 0.75))


@pytest.mark.parametrize(
    ("gold", "predicted", "matched"),
    [(2, 0, 0), (0, 2, 0), (2, 2, 0)],
    ids=["nothing-predicted", "nothing-in-gold", "nothing-matched"],
)
def test_entity_f1_is_zero_when_nothing_matches(gold, predicted, matched):
    # Arrange
    score = EntityScore(gold=gold, predicted=predicted, matched=matched)

    # Act / Assert
    assert score.f1 == 0.0


def test_entity_f1_is_none_without_gold_and_predictions():
    # Act / Assert
    assert EntityScore().f1 is None


@pytest.mark.parametrize(
    ("reference", "hypothesis", "expected"),
    [
        ("zmiana 12 mm", "zmiana 12 mm", 0.0),
        ("zmiana 12 mm", "zmiana 13 mm", 1 / 12),
        ("zmiana\n12 mm", "zmiana 12   mm", 0.0),
        ("", "", 0.0),
        ("", "cokolwiek", 1.0),
    ],
    ids=["identical", "one-substitution", "whitespace-ignored", "both-empty", "empty-reference"],
)
def test_char_error_rate(reference, hypothesis, expected):
    # Act
    cer = OCRScore.char_error_rate(reference, hypothesis)

    # Assert
    assert cer == pytest.approx(expected)


def test_char_error_rate_normalises_both_texts_first():
    # Arrange: the header and footer are not report text, so they are not OCR errors.
    reference = "Opis badania:\nzmiana 12 mm"
    hypothesis = "SZPITAL\nOpis badania:\nzmiana 12 mm\nWykonał/a: dr Test"

    # Act
    normalised = OCRScore.char_error_rate(reference, hypothesis)
    raw = OCRScore.char_error_rate(reference, hypothesis, normalize=False)

    # Assert
    assert normalised == 0.0
    assert raw > 0.0


def test_ocr_score_mean_and_worst_document():
    # Arrange
    score = OCRScore()

    # Act
    score.add("a", "zmiana 12 mm", "zmiana 12 mm")
    score.add("b", "zmiana 12 mm", "zmiana 13 mm")

    # Assert
    assert score.mean == pytest.approx(1 / 24)
    assert score.worst == ("b", pytest.approx(1 / 12))


def test_empty_ocr_score_has_no_mean_or_worst():
    # Act / Assert
    assert OCRScore().mean is None
    assert OCRScore().words_mean is None
    assert OCRScore().worst is None


@pytest.mark.parametrize(
    ("reference", "hypothesis", "expected"),
    [
        ("zmiana 12 mm", "zmiana 12 mm", 0.0),
        ("zmiana 12 mm\nBI-RADS 3", "BI-RADS 3\nzmiana 12 mm", 0.0),
        ("zmiana 12 mm", "zmiana 13 mm", 1 / 3),
        ("zmiana 12 mm", "zmiana mm", 1 / 3),
        ("zmiana 12 mm", "zmiana 12 mm ok", 1 / 3),
        ("", "", 0.0),
        ("", "cokolwiek", 1.0),
    ],
    ids=[
        "identical",
        "lines-swapped",
        "one-wrong-word",
        "missing-word",
        "extra-word",
        "both-empty",
        "empty-reference",
    ],
)
def test_bag_of_words_error_rate(reference, hypothesis, expected):
    # Act
    rate = OCRScore.bag_of_words_error_rate(reference, hypothesis)

    # Assert
    assert rate == pytest.approx(expected)


def test_swapped_lines_cost_cer_but_not_the_bag_of_words_rate():
    # Arrange: the same text, OCR read the second line first
    reference = "zmiana hipoechogeniczna 12 mm\nwniosek BI-RADS 3"
    hypothesis = "wniosek BI-RADS 3\nzmiana hipoechogeniczna 12 mm"
    score = OCRScore()

    # Act
    score.add("doc", reference, hypothesis)

    # Assert
    assert score.documents["doc"] > 0.3
    assert score.words["doc"] == 0.0
