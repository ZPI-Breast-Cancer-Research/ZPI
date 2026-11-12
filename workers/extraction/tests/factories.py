"""Synthetic test data and fakes shared by unit and integration tests.

Everything here is written for the tests: no real patient report is used anywhere.
"""

from collections.abc import Iterable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from workers.extraction.errors import LLMError, OcrError
from workers.extraction.llm import LLMResponse, Message
from workers.extraction.ocr import OcrLine, OcrPage
from workers.extraction.schema import (
    Brzeg,
    Echogenicznosc,
    EkstrakcjaBadania,
    ExtractionResult,
    Jednostka,
    KategoriaBiRads,
    Ksztalt,
    Kwalifikator,
    Miara,
    Modalnosc,
    Obserwacja,
    Piers,
    Piersi,
    PolaczenieObserwacji,
    Provenance,
    Skora,
    Strona,
    Wezel,
    Wniosek,
    Wymiary,
    Zmiana,
)

MMG_QUOTE = (
    "W piersi prawej w kwadrancie górnym zewnętrznym owalna zmiana o obwiedzionych zarysach, "
    "wym 12x8mm."
)
USG_QUOTE = (
    "W USG w piersi prawej na godz 10 owalna hipoechogeniczna zmiana ogniskowa o wym 11x7mm, "
    "3cm od brodawki, odpowiada zmianie w mammografii."
)
NODE_QUOTE = "Węzły chłonne w dole pachowym prawym niepowiększone."

# A synthetic MMG + USG report: a header to cut, the body, a footer to cut.
REPORT = "\n".join(
    [
        "SZPITAL TESTOWY",
        "Pacjentka: Anna Testowa",
        "Opis badania:",
        "Mammografia: piersi o budowie tłuszczowo-gruczołowej.",
        MMG_QUOTE,
        "Skóra prawidłowa.",
        USG_QUOTE,
        "W piersi lewej zmian ogniskowych nie stwierdza się.",
        NODE_QUOTE,
        "R. Zmiana w piersi prawej prawdopodobnie łagodna - BIRADS 3 - kontrola za 6 miesięcy.",
        "Wykonał/a: dr Test",
        "",
    ]
)


def mmg_obs(**overrides: Any) -> Obserwacja:
    """The mammography observation of the lesion in ``REPORT``."""
    values: dict[str, Any] = {
        "modalnosc": Modalnosc.MAMMOGRAFIA,
        "lokalizacje": ["kwadrancie górnym zewnętrznym"],
        "typ": "zmiana",
        "wymiary": Wymiary(
            wartosci=[12, 8], jednostka=Jednostka.MM, kwalifikator=Kwalifikator.DOKLADNY
        ),
        "ksztalt": Ksztalt.OWALNY,
        "brzeg": Brzeg.OBWIEDZIONY,
        "cytat": MMG_QUOTE,
    }
    return Obserwacja(**{**values, **overrides})


def usg_obs(**overrides: Any) -> Obserwacja:
    """The USG observation of the lesion in ``REPORT``."""
    values: dict[str, Any] = {
        "modalnosc": Modalnosc.USG,
        "godzina": "10",
        "odleglosc_od_brodawki": Miara(wartosc=3, jednostka=Jednostka.CM),
        "typ": "zmiana ogniskowa",
        "wymiary": Wymiary(
            wartosci=[11, 7], jednostka=Jednostka.MM, kwalifikator=Kwalifikator.DOKLADNY
        ),
        "ksztalt": Ksztalt.OWALNY,
        "echogenicznosc": Echogenicznosc.HIPOECHOGENICZNA,
        "cytat": USG_QUOTE,
    }
    return Obserwacja(**{**values, **overrides})


def lesion(**overrides: Any) -> Zmiana:
    """The one lesion of ``REPORT``, seen in both modalities."""
    values: dict[str, Any] = {
        "id": 1,
        "strona": Strona.PRAWA,
        "obserwacje": [mmg_obs(), usg_obs()],
        "polaczenie_obserwacji": PolaczenieObserwacji(pewne=True),
    }
    return Zmiana(**{**values, **overrides})


def node(**overrides: Any) -> Wezel:
    values: dict[str, Any] = {
        "modalnosc": Modalnosc.USG,
        "strona": Strona.PRAWA,
        "okolica": "dół pachowy",
        "patologiczne": False,
        "cytat": NODE_QUOTE,
    }
    return Wezel(**{**values, **overrides})


def breasts(**overrides: Any) -> Piersi:
    """Both breasts of ``REPORT``; ``overrides`` replace a whole side (``lewa=Piers(...)``)."""

    def side(focal: bool) -> Piers:
        return Piers(
            budowa="o budowie tłuszczowo-gruczołowej",
            zmiany_ogniskowe=focal,
            skora=Skora(stan="prawidłowa"),
        )

    return Piersi(**{"lewa": side(False), "prawa": side(True), **overrides})


def extraction(**overrides: Any) -> EkstrakcjaBadania:
    """A correct extraction of ``REPORT``: ``check_extraction`` finds nothing to warn about."""
    values: dict[str, Any] = {
        "modalnosci": [Modalnosc.MAMMOGRAFIA, Modalnosc.USG],
        "piersi": breasts(),
        "zmiany": [lesion()],
        "wezly": [node()],
        "wniosek": Wniosek(
            birads=KategoriaBiRads.K3,
            tekst="Zmiana w piersi prawej prawdopodobnie łagodna",
            zalecenie="kontrola za 6 miesięcy",
        ),
    }
    return EkstrakcjaBadania(**{**values, **overrides})


def provenance(**overrides: Any) -> Provenance:
    values: dict[str, Any] = {
        "llm_provider": "fake",
        "llm_model": "fake-model",
        "prompt_version": "v6",
        "few_shot": 1,
        "structured_output": True,
    }
    return Provenance(**{**values, **overrides})


def result(source: str = "doc1.txt", **overrides: Any) -> ExtractionResult:
    """A successful ``ExtractionResult`` of ``REPORT``."""
    values: dict[str, Any] = {
        "source": source,
        "status": "ok",
        "data": extraction(),
        "text": "Opis badania: syntetyczny tekst",
        "provenance": provenance(),
        "attempts": 1,
        "llm_seconds": 1.0,
        "created_at": datetime(2026, 1, 1, tzinfo=UTC),
    }
    return ExtractionResult(**{**values, **overrides})


def error_result(source: str = "doc1.txt", **overrides: Any) -> ExtractionResult:
    values: dict[str, Any] = {"status": "error", "data": None, "error": "LLM: down"}
    return result(source, **{**values, **overrides})


class FakeLLM:
    """``LLMClient`` that answers from a script: each item is the answer text or an exception."""

    provider = "fake"

    def __init__(self, answers: Iterable[str | Exception] = (), model: str = "fake-model"):
        self.model = model
        self._answers = list(answers)
        self.calls: list[dict[str, Any]] = []

    def list_models(self) -> list[str]:
        return [self.model]

    def complete(
        self,
        messages: list[Message],
        *,
        json_schema: dict[str, Any] | None = None,
        temperature: float = 0.0,
    ) -> LLMResponse:
        self.calls.append({"messages": messages, "json_schema": json_schema})
        if not self._answers:
            raise LLMError("FakeLLM: no scripted answer left")
        answer = self._answers.pop(0)
        if isinstance(answer, Exception):
            raise answer
        return LLMResponse(text=answer, model=self.model, seconds=0.5)


class FakeOcr:
    """``OcrEngine`` that returns given lines for every page, or raises for a page name."""

    name = "fake-ocr"
    version = "1.0"

    def __init__(self, lines: list[tuple[str, float]], *, fail_on: str | None = None):
        self._lines = lines
        self._fail_on = fail_on
        self.read: list[str] = []

    def read_page(self, image: Path) -> OcrPage:
        self.read.append(image.name)
        if image.name == self._fail_on:
            raise OcrError(f"cannot read {image.name}")
        return OcrPage(source=image.name, lines=[OcrLine(text, conf) for text, conf in self._lines])


def answer_json(data: EkstrakcjaBadania | None = None) -> str:
    """What a well-behaved LLM returns for ``REPORT``."""
    return (data or extraction()).model_dump_json()
