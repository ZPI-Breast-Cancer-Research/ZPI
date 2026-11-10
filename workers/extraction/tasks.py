import tempfile
from functools import cache
from pathlib import Path
from typing import Any

from common.storage import BUCKET_REPORTS, download_file
from config.celery import app

from .config import Settings
from .llm import LLMClient, get_llm_client
from .ocr import OcrEngine, get_ocr_engine
from .orientation import OrientationDetector, get_orientation_detector
from .pipeline import extract_from_images, extract_from_text


@cache
def _settings() -> Settings:
    return Settings.from_env()


@cache
def _llm() -> LLMClient:
    return get_llm_client(_settings())


@cache
def _ocr() -> OcrEngine:
    settings = _settings()
    return get_ocr_engine(settings.ocr_engine, lang=settings.ocr_lang)


@cache
def _orientation() -> OrientationDetector | None:
    return get_orientation_detector(_settings().ocr_orientation)


@app.task(name="extraction.run")
def run(keys: list[str], source: str | None = None) -> dict[str, Any]:
    settings = _settings()
    llm = _llm()
    source = source or Path(keys[0]).name
    few_shot = settings.few_shot_examples
    structured_output = settings.llm_structured_output
    with tempfile.TemporaryDirectory() as tmp:
        paths = [
            download_file(BUCKET_REPORTS, key, Path(tmp) / f"{i:03d}{Path(key).suffix}")
            for i, key in enumerate(keys)
        ]
        if paths[0].suffix.lower() == ".txt":
            result = extract_from_text(
                paths[0].read_text(encoding="utf-8"),
                llm,
                source=source,
                few_shot=few_shot,
                structured_output=structured_output,
            )
        else:
            result = extract_from_images(
                paths,
                _ocr(),
                llm,
                orientation=_orientation(),
                source=source,
                few_shot=few_shot,
                structured_output=structured_output,
            )
    return result.model_dump(mode="json")
