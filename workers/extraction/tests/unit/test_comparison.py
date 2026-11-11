from workers.extraction.evaluation.comparison import Comparison
from workers.extraction.evaluation.scores import EntityScore, FieldScore
from workers.extraction.schema import (
    Jednostka,
    KategoriaBiRads,
    Kwalifikator,
    Modalnosc,
    Wniosek,
    Wymiary,
)
from workers.extraction.tests.factories import extraction, lesion, mmg_obs, usg_obs


def compare(gold, pred):
    comparison = Comparison()
    comparison.document(gold, pred)
    return comparison.report


def test_identical_documents_are_all_correct():
    # Act
    report = compare(extraction(), extraction())

    # Assert
    overall = report.group_score()
    assert overall.n > 0
    assert overall.correct == overall.n
    assert report.entities["zmiany"] == EntityScore(gold=1, predicted=1, matched=1)


def test_field_outcomes_correct_wrong_missed_spurious():
    # Arrange
    gold = extraction(wniosek=Wniosek(birads=KategoriaBiRads.K3, tekst=None, zalecenie="kontrola"))
    wrong = extraction(wniosek=Wniosek(birads=KategoriaBiRads.K4, tekst=None, zalecenie="kontrola"))
    missed = extraction(wniosek=Wniosek(birads=None, tekst=None, zalecenie="kontrola"))
    spurious = extraction(
        wniosek=Wniosek(birads=KategoriaBiRads.K3, tekst="dodatek", zalecenie="kontrola")
    )

    # Act
    reports = [compare(gold, pred) for pred in (gold, wrong, missed, spurious)]

    # Assert
    assert reports[0].fields["wniosek.birads"] == FieldScore(correct=1)
    assert reports[1].fields["wniosek.birads"] == FieldScore(wrong=1)
    assert reports[2].fields["wniosek.birads"] == FieldScore(missed=1)
    assert reports[3].fields["wniosek.tekst"] == FieldScore(spurious=1)


def test_field_empty_in_both_is_not_counted():
    # Arrange
    data = extraction(wniosek=Wniosek(birads=KategoriaBiRads.K3))

    # Act
    report = compare(data, data)

    # Assert
    assert "wniosek.tekst" not in report.fields


def test_verbatim_text_tolerates_small_differences():
    # Arrange
    gold = extraction(wniosek=Wniosek(tekst="Zmiana w piersi prawej prawdopodobnie łagodna"))
    close = extraction(wniosek=Wniosek(tekst="zmiana w piersi prawej prawdopodobnie lagodna."))
    far = extraction(wniosek=Wniosek(tekst="Zmiana podejrzana"))

    # Act
    close_report = compare(gold, close)
    far_report = compare(gold, far)

    # Assert
    assert close_report.fields["wniosek.tekst"] == FieldScore(correct=1)
    assert far_report.fields["wniosek.tekst"] == FieldScore(wrong=1)


def test_size_in_another_unit_is_the_same_max_mm():
    # Arrange
    in_cm = Wymiary(wartosci=[1.2, 0.8], jednostka=Jednostka.CM, kwalifikator=Kwalifikator.DOKLADNY)
    gold = extraction(zmiany=[lesion(obserwacje=[mmg_obs()], polaczenie_obserwacji=None)])
    pred = extraction(
        zmiany=[lesion(obserwacje=[mmg_obs(wymiary=in_cm)], polaczenie_obserwacji=None)]
    )

    # Act
    report = compare(gold, pred)

    # Assert
    assert report.fields["obserwacja.mammografia.wymiary.max_mm"] == FieldScore(correct=1)
    assert report.fields["obserwacja.mammografia.wymiary.jednostka"] == FieldScore(wrong=1)


def test_locations_are_compared_as_a_set():
    # Arrange
    gold = extraction(
        zmiany=[
            lesion(
                obserwacje=[mmg_obs(lokalizacje=["KGZ", "Kwadrant dolny"])],
                polaczenie_obserwacji=None,
            )
        ]
    )
    pred = extraction(
        zmiany=[
            lesion(
                obserwacje=[mmg_obs(lokalizacje=["kwadrant dolny", "kgz"])],
                polaczenie_obserwacji=None,
            )
        ]
    )

    # Act
    report = compare(gold, pred)

    # Assert
    assert report.fields["obserwacja.mammografia.lokalizacje"] == FieldScore(correct=1)


def test_lesions_pair_by_quote_only_within_the_same_modality():
    # Arrange: same quote, but the prediction calls it USG.
    gold = extraction(zmiany=[lesion(obserwacje=[mmg_obs()], polaczenie_obserwacji=None)])
    pred = extraction(
        zmiany=[
            lesion(
                obserwacje=[usg_obs(cytat=mmg_obs().cytat)],
                polaczenie_obserwacji=None,
            )
        ]
    )

    # Act
    report = compare(gold, pred)

    # Assert
    assert report.entities["zmiany"] == EntityScore(gold=1, predicted=1, matched=0)
    assert "zmiana.strona" not in report.fields


def test_unpaired_lesion_counts_only_in_the_entity_score():
    # Arrange: the prediction adds a second lesion the gold doesn't have.
    extra = lesion(
        id=2,
        obserwacje=[usg_obs(cytat="Torbiel prosta 4 mm w piersi lewej.")],
        polaczenie_obserwacji=None,
    )
    gold = extraction()
    pred = extraction(zmiany=[lesion(), extra])

    # Act
    report = compare(gold, pred)

    # Assert
    assert report.entities["zmiany"] == EntityScore(gold=1, predicted=2, matched=1)
    assert report.fields["zmiana.strona"] == FieldScore(correct=1)


def test_modalities_compared_regardless_of_order():
    # Arrange
    gold = extraction(modalnosci=[Modalnosc.MAMMOGRAFIA, Modalnosc.USG])
    pred = extraction(modalnosci=[Modalnosc.USG, Modalnosc.MAMMOGRAFIA])

    # Act
    report = compare(gold, pred)

    # Assert
    assert report.fields["modalnosci"] == FieldScore(correct=1)
