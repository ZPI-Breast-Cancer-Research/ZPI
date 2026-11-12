import pytest

from workers.extraction.normalize import normalize_text


def test_header_before_report_start_is_cut():
    # Arrange
    text = "SZPITAL TESTOWY\nPacjentka: Anna Testowa\nOpis badania:\nZmiana 12 mm."

    # Act
    result = normalize_text(text)

    # Assert
    assert result == "Opis badania:\nZmiana 12 mm."


@pytest.mark.parametrize(
    "footer",
    ["Wykonał/a: dr Test", "Wykonat/a: dr Test", "Opis: dr Test"],
    ids=["wykonal", "ocr-typo-wykonat", "opis"],
)
def test_footer_is_cut(footer):
    # Arrange
    text = f"Opis badania:\nZmiana 12 mm.\n{footer}"

    # Act
    result = normalize_text(text)

    # Assert
    assert result == "Opis badania:\nZmiana 12 mm."


def test_report_start_label_does_not_count_as_footer():
    # Arrange: "Opis badania:" itself must not end the text at "Opis".
    text = "Opis badania: zmiana 5 mm."

    # Act
    result = normalize_text(text)

    # Assert
    assert result == "Opis badania: zmiana 5 mm."


def test_text_without_report_start_is_kept_whole():
    # Arrange
    text = "Zmiana w piersi prawej 12 mm.\nBIRADS 3"

    # Act
    result = normalize_text(text)

    # Assert
    assert result == text


def test_word_hyphenated_across_lines_is_joined():
    # Arrange
    text = "Opis badania:\nzmiana hipoecho-\ngeniczna"

    # Act
    result = normalize_text(text)

    # Assert
    assert result == "Opis badania:\nzmiana hipoechogeniczna"


def test_number_range_across_lines_keeps_its_break():
    # Arrange
    text = "Opis badania:\nwymiary 2-\n3 cm"

    # Act
    result = normalize_text(text)

    # Assert
    assert result == "Opis badania:\nwymiary 2-\n3 cm"


def test_spaces_collapse_and_lines_are_stripped():
    # Arrange
    text = "Opis badania:\n  zmiana \t  12   mm  "

    # Act
    result = normalize_text(text)

    # Assert
    assert result == "Opis badania:\nzmiana 12 mm"


def test_windows_line_endings_and_control_characters_are_removed():
    # Arrange
    text = "Opis badania:\r\nzmiana\x0c 12 mm\rBIRADS 3"

    # Act
    result = normalize_text(text)

    # Assert
    assert result == "Opis badania:\nzmiana 12 mm\nBIRADS 3"


def test_many_blank_lines_become_one():
    # Arrange
    text = "Opis badania:\nMMG\n\n\n\nUSG"

    # Act
    result = normalize_text(text)

    # Assert
    assert result == "Opis badania:\nMMG\n\nUSG"


def test_words_and_numbers_are_never_changed():
    # Arrange: OCR errors (0 for O, l for ł) stay as they are.
    text = "Opis badania:\nzmiana 9-0cm, ma1a, zmiana lagodna 4,5 mm"

    # Act
    result = normalize_text(text)

    # Assert
    assert result == text
