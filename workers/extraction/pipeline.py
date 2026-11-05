import tempfile
import time
from datetime import UTC, datetime
from pathlib import Path

from .llm.base import LLMClient, LLMError, Message
from .normalize import normalize_text
from .ocr.base import OcrEngine, OcrPage, OcrResult
from .orientation import OrientationDetector, make_upright
from .schema import ExtractionResult, Provenance, llm_json_schema
from .structuring.checks import check_extraction
from .structuring.parsing import ParseError, parse_response
from .structuring.prompting import PROMPT_VERSION, build_messages

MAX_ATTEMPTS = 2


def run_ocr(
    images: list[Path], ocr: OcrEngine, orientation: OrientationDetector | None = None
) -> OcrResult:
    started = time.perf_counter()
    with tempfile.TemporaryDirectory() as tmp:
        pages = [_read_upright(image, ocr, orientation, Path(tmp)) for image in images]
    return OcrResult(
        engine=ocr.name,
        engine_version=ocr.version,
        pages=pages,
        seconds=time.perf_counter() - started,
        orientation=orientation.name if orientation else None,
    )


def _read_upright(
    image: Path, ocr: OcrEngine, orientation: OrientationDetector | None, tmp: Path
) -> OcrPage:
    if orientation is None:
        return ocr.read_page(image)
    upright, angle = make_upright(image, orientation, tmp)
    page = ocr.read_page(upright)
    page.source = image.name
    page.rotation = angle
    return page


def extract_from_images(
    images: list[Path],
    ocr: OcrEngine,
    llm: LLMClient,
    *,
    orientation: OrientationDetector | None = None,
    source: str | None = None,
    few_shot: int = 1,
    structured_output: bool = True,
) -> ExtractionResult:
    source = source or images[0].name
    try:
        ocr_result = run_ocr(images, ocr, orientation)
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
    result.provenance.orientation_detector = ocr_result.orientation
    result.provenance.page_rotations = [page.rotation for page in ocr_result.pages]
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
        return _error_result(source, "Empty report text (did OCR read nothing?)", text, llm)

    messages = build_messages(text, few_shot=few_shot)
    schema = llm_json_schema() if structured_output else None
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

    result = _error_result(source, f"Parsing: {last_error}", text, llm, attempts=MAX_ATTEMPTS)
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
