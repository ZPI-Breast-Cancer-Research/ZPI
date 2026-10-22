import time
from datetime import UTC, datetime
from pathlib import Path

from .checks import check_extraction
from .llm.base import LLMClient, LLMError, Message
from .normalize import normalize_text
from .ocr.base import OcrEngine, OcrResult
from .parsing import ParseError, parse_response
from .prompting import PROMPT_VERSION, build_messages
from .schema import EkstrakcjaBadania, ExtractionResult, Provenance

MAX_ATTEMPTS = 2


def run_ocr(images: list[Path], ocr: OcrEngine) -> OcrResult:
    started = time.perf_counter()
    pages = [ocr.read_page(image) for image in images]
    return OcrResult(
        engine=ocr.name,
        engine_version=ocr.version,
        pages=pages,
        seconds=time.perf_counter() - started,
    )


def extract_from_images(
    images: list[Path],
    ocr: OcrEngine,
    llm: LLMClient,
    *,
    source: str | None = None,
    few_shot: int = 1,
    structured_output: bool = True,
) -> ExtractionResult:
    source = source or images[0].name
    try:
        ocr_result = run_ocr(images, ocr)
    except Exception as exc:
        return _error_result(source, f"OCR: {exc}", text="", llm=llm)

    result = extract_from_text(
        ocr_result.text,
        llm,
        source=source,
        few_shot=few_shot,
        structured_output=structured_output,
    )
    result.provenance.ocr_engine = ocr_result.engine
    result.provenance.ocr_engine_version = ocr_result.engine_version
    result.provenance.ocr_mean_confidence = ocr_result.mean_confidence
    result.ocr_seconds = round(ocr_result.seconds, 2)
    return result


def extract_from_text(
    text: str,
    llm: LLMClient,
    *,
    source: str = "text",
    few_shot: int = 1,
    structured_output: bool = True,
) -> ExtractionResult:
    text = normalize_text(text)
    if not text:
        return _error_result(source, "Pusty tekst opisu (OCR nic nie odczytał?)", text, llm)

    messages = build_messages(text, few_shot=few_shot)
    schema = EkstrakcjaBadania.model_json_schema() if structured_output else None
    llm_seconds = 0.0
    last_error = ""

    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            response = llm.complete(messages, json_schema=schema)
        except LLMError as exc:
            return _error_result(source, f"LLM: {exc}", text, llm, attempts=attempt)
        llm_seconds += response.seconds

        try:
            data = parse_response(response.text)
        except ParseError as exc:
            last_error = str(exc)
            messages = [*messages, *_retry_messages(response.text, last_error)]
            continue

        return ExtractionResult(
            source=source,
            status="ok",
            data=data,
            warnings=check_extraction(data, text),
            text=text,
            provenance=_provenance(llm),
            attempts=attempt,
            llm_seconds=round(llm_seconds, 2),
            created_at=datetime.now(UTC),
        )

    result = _error_result(source, f"Parsowanie: {last_error}", text, llm, attempts=MAX_ATTEMPTS)
    result.llm_seconds = round(llm_seconds, 2)
    return result


def _retry_messages(answer: str, error: str) -> list[Message]:
    return [
        {"role": "assistant", "content": answer},
        {
            "role": "user",
            "content": f"{error}\nPopraw odpowiedź. Zwróć wyłącznie poprawny obiekt JSON.",
        },
    ]


def _provenance(llm: LLMClient) -> Provenance:
    return Provenance(llm_provider=llm.provider, llm_model=llm.model, prompt_version=PROMPT_VERSION)


def _error_result(
    source: str, error: str, text: str, llm: LLMClient, *, attempts: int = 0
) -> ExtractionResult:
    return ExtractionResult(
        source=source,
        status="error",
        error=error,
        text=text,
        provenance=_provenance(llm),
        attempts=attempts,
        created_at=datetime.now(UTC),
    )
