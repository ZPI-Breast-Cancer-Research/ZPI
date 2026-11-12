import pytest

from workers.extraction.normalize import normalize_text
from workers.extraction.schema import (
    Brzeg,
    Echogenicznosc,
    Jednostka,
    Ksztalt,
    Kwalifikator,
    Modalnosc,
    Piers,
    PolaczenieObserwacji,
    Strona,
    Wniosek,
    Wymiary,
)
from workers.extraction.structuring.checks import check_extraction
from workers.extraction.tests.factories import (
    REPORT,
    breasts,
    extraction,
    lesion,
    mmg_obs,
    node,
    usg_obs,
)

TEXT = normalize_text(REPORT)


def lesion_with(*observations, **overrides):
    """One lesion; ``polaczenie_obserwacji`` only when there are several observations."""
    link = PolaczenieObserwacji(pewne=True) if len(observations) > 1 else None
    return lesion(obserwacje=list(observations), polaczenie_obserwacji=link, **overrides)


def test_consistent_extraction_has_no_warnings():
    # Act
    warnings = check_extraction(extraction(), TEXT)

    # Assert
    assert warnings == []


@pytest.mark.parametrize(
    ("data", "expected"),
    [
        pytest.param(
            extraction(zmiany=[lesion_with(usg_obs(cytat="Torbiel prosta w piersi lewej."))]),
            "obserwacja 1 (usg): cytatu nie znaleziono w opisie",
            id="observation-quote-not-in-report",
        ),
        pytest.param(
            extraction(wezly=[node(cytat="Węzeł podobojczykowy powiększony do 25 mm.")]),
            "węzeł 1: cytatu nie znaleziono w opisie",
            id="node-quote-not-in-report",
        ),
        pytest.param(
            extraction(piersi=breasts(lewa=Piers(budowa="o przewadze utkania tłuszczowego"))),
            "pierś lewa: budowa „o przewadze utkania tłuszczowego”: "
            "w opisie brak słów przewadze, utkania",
            id="verbatim-budowa",
        ),
        pytest.param(
            extraction(wniosek=Wniosek(tekst="Podejrzenie raka piersi")),
            "wniosek: tekst „Podejrzenie raka piersi”: w opisie brak słów Podejrzenie, raka",
            id="verbatim-wniosek",
        ),
        pytest.param(
            extraction(wezly=[node(uwagi="powiększone, zatarta wnęka")]),
            "węzeł 1: uwagi",
            id="verbatim-node-remarks",
        ),
        pytest.param(
            extraction(
                zmiany=[
                    lesion_with(
                        mmg_obs(
                            wymiary=Wymiary(
                                wartosci=[15, 8],
                                jednostka=Jednostka.MM,
                                kwalifikator=Kwalifikator.DOKLADNY,
                            )
                        ),
                        usg_obs(),
                    )
                ]
            ),
            "obserwacja 1 (mammografia): wymiary 15 nie występuje w cytacie",
            id="size-not-in-quote",
        ),
        pytest.param(
            extraction(zmiany=[lesion_with(mmg_obs(), usg_obs(godzina="2"))]),
            "obserwacja 2 (usg): godzina 2 nie występuje w cytacie",
            id="clock-not-in-quote",
        ),
        pytest.param(
            extraction(
                wezly=[
                    node(
                        wymiary=Wymiary(
                            wartosci=[9], jednostka=Jednostka.MM, kwalifikator=Kwalifikator.DOKLADNY
                        )
                    )
                ]
            ),
            "węzeł 1: wymiary 9 nie występuje w cytacie",
            id="node-size-not-in-quote",
        ),
        pytest.param(
            extraction(zmiany=[lesion_with(mmg_obs(ksztalt=Ksztalt.NIEREGULARNY), usg_obs())]),
            "ksztalt = nieregularny nie wynika z cytatu",
            id="shape-not-in-quote",
        ),
        pytest.param(
            extraction(zmiany=[lesion_with(mmg_obs(brzeg=Brzeg.SPIKULARNY), usg_obs())]),
            "brzeg = spikularny nie wynika z cytatu",
            id="margin-not-in-quote",
        ),
        pytest.param(
            extraction(
                zmiany=[lesion_with(mmg_obs(), usg_obs(echogenicznosc=Echogenicznosc.BEZECHOWA))]
            ),
            "echogenicznosc = bezechowa nie wynika z cytatu",
            id="echogenicity-not-in-quote",
        ),
        pytest.param(
            extraction(
                zmiany=[
                    lesion_with(mmg_obs(echogenicznosc=Echogenicznosc.HIPOECHOGENICZNA), usg_obs())
                ]
            ),
            "obserwacja 1 (mammografia): pole echogenicznosc dotyczy tylko USG",
            id="usg-only-field-in-mammography",
        ),
        pytest.param(
            extraction(zmiany=[lesion(), lesion()]),
            "powtórzone numery zmian (id)",
            id="duplicate-lesion-ids",
        ),
        pytest.param(
            extraction(zmiany=[lesion_with()]),
            "zmiana 1: brak obserwacji",
            id="lesion-without-observations",
        ),
        pytest.param(
            extraction(zmiany=[lesion(polaczenie_obserwacji=None)]),
            "zmiana 1: kilka obserwacji bez polaczenie_obserwacji",
            id="several-observations-without-link",
        ),
        pytest.param(
            extraction(
                zmiany=[
                    lesion(
                        obserwacje=[usg_obs()],
                        polaczenie_obserwacji=PolaczenieObserwacji(pewne=True),
                    )
                ]
            ),
            "zmiana 1: polaczenie_obserwacji przy jednej obserwacji",
            id="link-with-one-observation",
        ),
        pytest.param(
            extraction(zmiany=[lesion(strona=Strona.LEWA)]),
            "zmiana 1: pierś lewa ma zmiany_ogniskowe = false",
            id="lesion-in-breast-without-focal-lesions",
        ),
        pytest.param(
            extraction(zmiany=[lesion(strona=Strona.OBUSTRONNIE)]),
            "zmiana 1: pierś lewa ma zmiany_ogniskowe = false",
            id="bilateral-lesion-checks-both-breasts",
        ),
    ],
)
def test_inconsistency_is_reported(data, expected):
    # Act
    warnings = check_extraction(data, TEXT)

    # Assert
    assert any(expected in w for w in warnings), warnings


@pytest.mark.parametrize(
    ("quote", "value"),
    [
        ("zmiana obniżonej echogeniczności 5 mm", Echogenicznosc.HIPOECHOGENICZNA),
        ("węzeł normoechogeniczny 5 mm", Echogenicznosc.IZOECHOGENICZNA),
        ("zmiana hypoechogeniczna 5 mm", Echogenicznosc.HIPOECHOGENICZNA),
    ],
)
def test_echogenicity_synonyms_support_the_value(quote, value):
    # Arrange
    obs = usg_obs(
        cytat=quote,
        godzina=None,
        odleglosc_od_brodawki=None,
        ksztalt=None,
        typ=None,
        wymiary=None,
        echogenicznosc=value,
    )
    data = extraction(zmiany=[lesion_with(obs)])

    # Act
    warnings = check_extraction(data, quote)

    # Assert
    assert not [w for w in warnings if "echogenicznosc" in w], warnings


@pytest.mark.parametrize(
    ("quote", "warned"),
    [
        ("zmiana ostro odgraniczona 5 mm", False),
        ("zmiana o obwiedzionych zarysach 5 mm", False),
        # A stem must start a word: "nieostro" contains "ostro", but is the opposite.
        ("zmiana nieostro odgraniczona 5 mm", True),
    ],
)
def test_margin_stem_must_start_a_word(quote, warned):
    # Arrange
    obs = mmg_obs(
        cytat=quote, lokalizacje=[], typ=None, wymiary=None, ksztalt=None, brzeg=Brzeg.OBWIEDZIONY
    )
    data = extraction(zmiany=[lesion_with(obs)])

    # Act
    warnings = check_extraction(data, quote)

    # Assert
    margin_warnings = [w for w in warnings if "brzeg = obwiedziony" in w]
    assert bool(margin_warnings) is warned, warnings


def test_mammography_without_usg_fields_has_no_usg_warning():
    # Arrange
    data = extraction(zmiany=[lesion_with(mmg_obs())])

    # Act
    warnings = check_extraction(data, TEXT)

    # Assert
    assert not [w for w in warnings if "tylko USG" in w]
    assert Modalnosc.MAMMOGRAFIA == data.zmiany[0].obserwacje[0].modalnosc
