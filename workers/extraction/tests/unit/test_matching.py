import pytest

from workers.extraction.matching import fold, quote_similarity, text_similarity


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Hipo-echogeniczna  Ł", "hipoechogeniczna l"),
        ("ŻÓŁĆ gęślą jaźń", "zolc gesla jazn"),
        ("  zmiana\n\togniskowa ", "zmiana ogniskowa"),
    ],
)
def test_fold_drops_case_diacritics_hyphens_and_extra_whitespace(text, expected):
    # Act
    result = fold(text)

    # Assert
    assert result == expected


def test_quote_found_exactly_ignoring_case_scores_one():
    # Arrange
    haystack = fold("W USG zmiana hipoechogeniczna 12 mm.")

    # Act
    score = quote_similarity("Zmiana HIPOECHOGENICZNA", haystack)

    # Assert
    assert score == 1.0


def test_quote_with_ocr_typo_still_matches():
    # Arrange
    haystack = fold("W USG zmiana hipoechogeniczna 12 mm.")

    # Act
    score = quote_similarity("zmiana hipoechogenlczna", haystack)

    # Assert
    assert 0.85 <= score < 1.0


def test_unrelated_quote_scores_low():
    # Arrange
    haystack = fold("W USG zmiana hipoechogeniczna 12 mm.")

    # Act
    score = quote_similarity("torbiel prosta", haystack)

    # Assert
    assert score < 0.5


def test_empty_quote_scores_zero():
    # Act
    score = quote_similarity("  ", fold("dowolny tekst"))

    # Assert
    assert score == 0.0


def test_text_similarity_ignores_case_and_diacritics():
    # Act
    same = text_similarity("Zmiana łagodna", "zmiana lagodna")
    different = text_similarity("zmiana łagodna", "torbiel prosta")

    # Assert
    assert same == 1.0
    assert different < 0.5
