import tempfile
import time
from collections.abc import Callable
from datetime import UTC, datetime
from functools import cached_property, partial
from pathlib import Path

from .config import Settings
from .documents import Document
from .errors import LLMError, ParseError
from .llm import LLMClient, Message, get_llm_client
from .normalize import normalize_text
from .ocr import OcrEngine, OcrPage, OcrResult, get_ocr_engine
from .orientation import OrientationDetector, get_orientation_detector, make_upright
from .schema import ExtractionResult, Provenance, llm_json_schema
from .structuring.checks import check_extraction
from .structuring.parsing import parse_response
from .structuring.prompting import PROMPT_VERSION, build_messages

MAX_ATTEMPTS = 2


class Extractor:
    """The pipeline assembled from ``Settings``: one LLM client, OCR and orientation detector
    loaded on first use (a run over text files never loads them)."""

    def __init__(
        self,
        llm: LLMClient,
        *,
        ocr_engine: str = "paddle",
        ocr_lang: str = "pl",
        orientation: str = "paddle",
        few_shot: int = 1,
        structured_output: bool = True,
        log: Callable[[str], None] | None = None,
    ):
        self.llm = llm
        self.few_shot = few_shot
        self.structured_output = structured_output
        self._ocr_engine = ocr_engine
        self._ocr_lang = ocr_lang
        self._orientation = orientation
        self._log = log or (lambda message: None)

    @classmethod
    def from_settings(
        cls, settings: Settings, *, log: Callable[[str], None] | None = None
    ) -> "Extractor":
        llm = get_llm_client(
            settings.llm_provider,
            base_url=settings.llm_base_url,
            model=settings.llm_model,
            allowed_hosts=settings.llm_allowed_hosts,
            timeout=settings.llm_timeout,
        )
        return cls(
            llm,
            ocr_engine=settings.ocr_engine,
            ocr_lang=settings.ocr_lang,
            orientation=settings.ocr_orientation,
            few_shot=settings.few_shot_examples,
            structured_output=settings.llm_structured_output,
            log=log,
        )

    @cached_property
    def ocr(self) -> OcrEngine:
        self._log(f"Loading OCR: {self._ocr_engine} ...")
        return get_ocr_engine(self._ocr_engine, lang=self._ocr_lang)

    @cached_property
    def orientation(self) -> OrientationDetector | None:
        if self._orientation != "none":
            self._log(f"Loading orientation detector: {self._orientation} ...")
        return get_orientation_detector(self._orientation)

    def extract(self, document: Document) -> ExtractionResult:
        if document.is_text:
            return self.extract_text(
                document.files[0].read_text(encoding="utf-8"), source=document.source
            )
        return extract_from_images(
            document.files,
            self.ocr,
            self.llm,
            orientation=self.orientation,
            source=document.source,
            few_shot=self.few_shot,
            structured_output=self.structured_output,
        )

    def extract_text(self, text: str, *, source: str = "text") -> ExtractionResult:
        return extract_from_text(
            text,
            self.llm,
            source=source,
            few_shot=self.few_shot,
            structured_output=self.structured_output,
        )

    def run_ocr(self, images: list[Path]) -> OcrResult:
        return run_ocr(images, self.ocr, self.orientation)


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
        # OCR libraries raise anything; one unreadable scan must not stop a batch.
        provenance = _provenance(llm, few_shot, structured_output)
        return _error_result(source, f"OCR: {exc}", "", provenance)

    result = extract_from_text(
        ocr_result.text,
        llm,
        source=source,
        few_shot=few_shot,
        structured_output=structured_output,
    )
    _add_ocr_provenance(result, ocr_result)
    return result


def extract_from_text(
    text: str,
    llm: LLMClient,
    *,
    source: str = "text",
    few_shot: int = 1,
    structured_output: bool = True,
) -> ExtractionResult:
    # Built when the result is made: an auto-selected model is known only after the first call.
    provenance = partial(_provenance, llm, few_shot, structured_output)
    text = normalize_text(text)
    if not text:
        error = "Empty report text (did OCR read nothing?)"
        return _error_result(source, error, text, provenance())

    messages = build_messages(text, few_shot=few_shot)
    schema = llm_json_schema() if structured_output else None
    llm_seconds = 0.0
    last_error = ""

    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            response = llm.complete(messages, json_schema=schema)
        except LLMError as exc:
            return _error_result(source, f"LLM: {exc}", text, provenance(), attempts=attempt)
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
            provenance=provenance(),
            attempts=attempt,
            llm_seconds=round(llm_seconds, 2),
            created_at=datetime.now(UTC),
        )

    result = _error_result(
        source, f"Parsing: {last_error}", text, provenance(), attempts=MAX_ATTEMPTS
    )
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


def _provenance(llm: LLMClient, few_shot: int, structured_output: bool) -> Provenance:
    return Provenance(
        llm_provider=llm.provider,
        llm_model=llm.model,
        prompt_version=PROMPT_VERSION,
        few_shot=few_shot,
        structured_output=structured_output,
    )


def _add_ocr_provenance(result: ExtractionResult, ocr_result: OcrResult) -> None:
    result.provenance.ocr_engine = ocr_result.engine
    result.provenance.ocr_engine_version = ocr_result.engine_version
    result.provenance.ocr_mean_confidence = ocr_result.mean_confidence
    result.provenance.orientation_detector = ocr_result.orientation
    result.provenance.page_rotations = [page.rotation for page in ocr_result.pages]
    result.ocr_seconds = round(ocr_result.seconds, 2)


def _error_result(
    source: str, error: str, text: str, provenance: Provenance, *, attempts: int = 0
) -> ExtractionResult:
    return ExtractionResult(
        source=source,
        status="error",
        error=error,
        text=text,
        provenance=provenance,
        attempts=attempts,
        created_at=datetime.now(UTC),
    )
