"""The extraction pipeline end to end, with a scripted LLM and OCR instead of real models."""

from pathlib import Path

from workers.extraction.documents import Document
from workers.extraction.errors import LLMError
from workers.extraction.pipeline import Extractor, extract_from_images, extract_from_text
from workers.extraction.schema import KategoriaBiRads, Ksztalt, Wniosek
from workers.extraction.structuring.prompting import PROMPT_VERSION
from workers.extraction.tests.factories import (
    REPORT,
    FakeLLM,
    FakeOcr,
    answer_json,
    extraction,
    lesion,
    mmg_obs,
    usg_obs,
)


def test_valid_answer_gives_ok_result_with_provenance():
    # Arrange
    llm = FakeLLM([answer_json()])

    # Act
    result = extract_from_text(REPORT, llm, source="doc1.txt", few_shot=1)

    # Assert
    assert result.status == "ok"
    assert result.data == extraction()
    assert result.warnings == []
    assert result.attempts == 1
    assert result.source == "doc1.txt"
    assert result.provenance.llm_model == "fake-model"
    assert result.provenance.prompt_version == PROMPT_VERSION
    assert result.provenance.few_shot == 1
    assert result.provenance.structured_output is True
    assert result.provenance.ocr_engine is None


def test_text_sent_to_the_llm_is_normalised():
    # Arrange
    llm = FakeLLM([answer_json()])

    # Act
    result = extract_from_text(REPORT, llm)

    # Assert
    sent = llm.calls[0]["messages"][-1]["content"]
    assert "SZPITAL TESTOWY" not in sent
    assert "Wykonał/a" not in sent
    assert result.text.startswith("Opis badania:")


def test_answer_inconsistent_with_report_gives_warnings():
    # Arrange
    wrong = extraction(
        zmiany=[lesion(obserwacje=[mmg_obs(ksztalt=Ksztalt.NIEREGULARNY), usg_obs()])]
    )
    llm = FakeLLM([answer_json(wrong)])

    # Act
    result = extract_from_text(REPORT, llm)

    # Assert
    assert result.status == "ok"
    assert any("ksztalt = nieregularny" in w for w in result.warnings)


def test_bad_first_answer_is_retried_with_the_error():
    # Arrange
    llm = FakeLLM(['{"modalnosci": "nie lista"}', answer_json()])

    # Act
    result = extract_from_text(REPORT, llm)

    # Assert
    assert result.status == "ok"
    assert result.attempts == 2
    retry = llm.calls[1]["messages"]
    assert retry[-2] == {"role": "assistant", "content": '{"modalnosci": "nie lista"}'}
    assert "JSON does not match the schema" in retry[-1]["content"]


def test_two_bad_answers_give_a_parsing_error():
    # Arrange
    llm = FakeLLM(["nie wiem", "nadal nie wiem"])

    # Act
    result = extract_from_text(REPORT, llm)

    # Assert
    assert result.status == "error"
    assert result.data is None
    assert result.error.startswith("Parsing:")
    assert result.attempts == 2
    assert result.llm_seconds == 1.0


def test_llm_failure_gives_an_error_result_instead_of_raising():
    # Arrange
    llm = FakeLLM([LLMError("connection refused")])

    # Act
    result = extract_from_text(REPORT, llm)

    # Assert
    assert result.status == "error"
    assert result.error == "LLM: connection refused"
    assert result.attempts == 1


def test_empty_text_is_an_error_without_calling_the_llm():
    # Arrange
    llm = FakeLLM([answer_json()])

    # Act
    result = extract_from_text("  \n\n ", llm)

    # Assert
    assert result.status == "error"
    assert "Empty report text" in result.error
    assert llm.calls == []


def test_structured_output_sends_the_json_schema_only_when_enabled():
    # Arrange
    with_schema, without_schema = FakeLLM([answer_json()]), FakeLLM([answer_json()])

    # Act
    extract_from_text(REPORT, with_schema, structured_output=True)
    result = extract_from_text(REPORT, without_schema, structured_output=False)

    # Assert
    assert with_schema.calls[0]["json_schema"] is not None
    assert without_schema.calls[0]["json_schema"] is None
    assert result.provenance.structured_output is False


def test_few_shot_zero_sends_no_example():
    # Arrange
    llm = FakeLLM([answer_json()])

    # Act
    extract_from_text(REPORT, llm, few_shot=0)

    # Assert
    assert [m["role"] for m in llm.calls[0]["messages"]] == ["system", "user"]


def test_images_go_through_ocr_then_the_llm():
    # Arrange
    ocr = FakeOcr([(line, 0.9) for line in REPORT.splitlines()])
    llm = FakeLLM([answer_json()])
    pages = [Path("page1.jpg"), Path("page2.jpg")]

    # Act
    result = extract_from_images(pages, ocr, llm, orientation=None)

    # Assert
    assert ocr.read == ["page1.jpg", "page2.jpg"]
    assert result.status == "ok"
    assert result.source == "page1.jpg"
    assert "owalna hipoechogeniczna" in llm.calls[0]["messages"][-1]["content"]
    assert result.provenance.ocr_engine == "fake-ocr"
    assert result.provenance.ocr_engine_version == "1.0"
    assert result.provenance.ocr_mean_confidence == 0.9
    assert result.provenance.page_rotations == [None, None]
    assert result.ocr_seconds is not None


def test_ocr_failure_gives_an_error_result_instead_of_raising():
    # Arrange
    ocr = FakeOcr([("tekst", 0.9)], fail_on="page2.jpg")
    llm = FakeLLM([answer_json()])

    # Act
    result = extract_from_images([Path("page1.jpg"), Path("page2.jpg")], ocr, llm, source="skan")

    # Assert
    assert result.status == "error"
    assert result.error.startswith("OCR:")
    assert result.source == "skan"
    assert llm.calls == []


def test_extractor_on_a_text_document_never_loads_ocr(tmp_path):
    # Arrange: an unknown OCR engine would raise if anything tried to load it.
    path = tmp_path / "opis.txt"
    path.write_text(REPORT, encoding="utf-8")
    llm = FakeLLM([answer_json(extraction(wniosek=Wniosek(birads=KategoriaBiRads.K3)))])
    extractor = Extractor(llm, ocr_engine="does-not-exist", orientation="does-not-exist")

    # Act
    result = extractor.extract(Document("opis.txt", [path]))

    # Assert
    assert result.status == "ok"
    assert result.source == "opis.txt"
    assert result.data.wniosek.birads == KategoriaBiRads.K3
