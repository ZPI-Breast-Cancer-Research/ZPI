import pytest

from workers.extraction.schema import ExtractionResult
from workers.extraction.structuring import uncertainty as u
from workers.extraction.tests.factories import error_result, extraction, provenance, result

HEAVY_WARNING = "węzeł 1: cytatu nie znaleziono w opisie"
LIGHT_WARNING = "wniosek: tekst „x”: w opisie brak słów abcd"


def test_correct_text_result_is_certain():
    # Arrange
    res = result()

    # Act / Assert
    assert res.uncertainty == 0.0
    assert res.uncertainty_components == {"error": 0.0, "warnings": 0.0, "ocr": 0.0, "retry": 0.0}


def test_failed_extraction_has_maximum_uncertainty():
    # Arrange: a failed OCR read with a poor scan: still exactly 1.0
    res = error_result(provenance=provenance(ocr_mean_confidence=0.5))

    # Act / Assert
    assert res.uncertainty == 1.0
    assert res.uncertainty_components["error"] == 1.0


@pytest.mark.parametrize(
    ("warning", "weight"),
    [
        ("zmiana 1, obserwacja 1 (usg): cytatu nie znaleziono w opisie", u.HEAVY),
        ("zmiana 1, obserwacja 1 (usg): wymiary 14 nie występuje w cytacie", u.HEAVY),
        ("zmiana 1, obserwacja 1 (usg): ksztalt = owalny nie wynika z cytatu", u.MEDIUM),
        ("zmiana 1, obserwacja 1 (mammografia): pole glebokosc dotyczy tylko USG", u.MEDIUM),
        ("zmiana 1: pierś lewa ma zmiany_ogniskowe = false", u.MEDIUM),
        ("pierś lewa: budowa „x”: w opisie brak słów abcd", u.LIGHT),
        ("powtórzone numery zmian (id)", u.DEFAULT_WEIGHT),
    ],
)
def test_each_kind_of_warning_has_its_weight(warning, weight):
    # Act / Assert
    assert u.warning_weight(warning) == weight


def test_heavy_warning_counts_more_than_a_light_one():
    # Arrange
    heavy = result(warnings=[HEAVY_WARNING])
    light = result(warnings=[LIGHT_WARNING])

    # Act / Assert
    assert heavy.uncertainty > light.uncertainty > 0


def test_more_warnings_mean_more_uncertainty():
    # Arrange
    one = result(warnings=[HEAVY_WARNING])
    two = result(warnings=[HEAVY_WARNING, HEAVY_WARNING])

    # Act / Assert
    assert two.uncertainty > one.uncertainty


def test_same_warning_weighs_less_in_a_longer_report():
    # Arrange: the factory extraction has 2 observations and 1 node; drop them for a short one
    long = result(warnings=[HEAVY_WARNING])
    short = result(warnings=[HEAVY_WARNING], data=extraction(zmiany=[], wezly=[]))

    # Act / Assert
    assert short.uncertainty > long.uncertainty


@pytest.mark.parametrize(
    ("confidence", "expected"),
    [(None, 0.0), (0.99, 0.0), (0.95, 0.0), (0.875, 0.5), (0.8, 1.0), (0.3, 1.0)],
)
def test_ocr_component_grows_as_confidence_drops(confidence, expected):
    # Arrange
    res = result(provenance=provenance(ocr_mean_confidence=confidence))

    # Act / Assert
    assert res.uncertainty_components["ocr"] == pytest.approx(expected)


def test_second_llm_attempt_adds_uncertainty():
    # Arrange
    res = result(attempts=2)

    # Act / Assert
    assert res.uncertainty == u.RETRY


def test_components_are_joined_with_noisy_or():
    # Arrange
    res = result(attempts=2, provenance=provenance(ocr_mean_confidence=0.875))

    # Act / Assert: 1 - (1 - 0.2)(1 - 0.5)
    assert res.uncertainty == pytest.approx(0.6)


def test_uncertainty_stays_within_zero_and_one():
    # Arrange: everything at once
    res = result(
        warnings=[HEAVY_WARNING] * 20,
        attempts=2,
        provenance=provenance(ocr_mean_confidence=0.1),
    )

    # Act / Assert
    assert 0.0 <= res.uncertainty <= 1.0


def test_uncertainty_is_in_the_dump_and_recomputed_when_read_back():
    # Arrange: a saved result whose stored value is stale (e.g. an older formula)
    dumped = result(warnings=[HEAVY_WARNING]).model_dump(mode="json")
    dumped["uncertainty"] = 0.123

    # Act
    loaded = ExtractionResult.model_validate(dumped)

    # Assert
    assert "uncertainty_components" in dumped
    assert loaded.uncertainty == result(warnings=[HEAVY_WARNING]).uncertainty
    assert loaded.uncertainty != 0.123
