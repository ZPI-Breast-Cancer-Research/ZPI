import json

import pytest

from workers.extraction.errors import ParseError
from workers.extraction.structuring.parsing import parse_response
from workers.extraction.tests.factories import answer_json, extraction


def test_bare_json_is_parsed():
    # Act
    data = parse_response(answer_json())

    # Assert
    assert data == extraction()


def test_json_in_code_fence_is_parsed():
    # Arrange
    text = f"Oto wynik:\n```json\n{answer_json()}\n```\nKoniec."

    # Act
    data = parse_response(text)

    # Assert
    assert data == extraction()


def test_json_wrapped_in_prose_is_parsed():
    # Arrange
    text = f"Wynik ekstrakcji: {answer_json()} -- to wszystko."

    # Act
    data = parse_response(text)

    # Assert
    assert data == extraction()


@pytest.mark.parametrize("text", ["Nie umiem odpowiedzieć.", "} {"])
def test_answer_without_json_object_is_rejected(text):
    # Act / Assert
    with pytest.raises(ParseError, match="no JSON object"):
        parse_response(text)


def test_broken_json_is_rejected():
    # Act / Assert
    with pytest.raises(ParseError, match="not valid JSON"):
        parse_response('{"modalnosci": ["usg",]}')


def test_schema_violation_names_the_field():
    # Arrange
    data = json.loads(answer_json())
    data["zmiany"][0]["strona"] = "środek"

    # Act / Assert
    with pytest.raises(ParseError, match=r"zmiany\.0\.strona"):
        parse_response(json.dumps(data))
