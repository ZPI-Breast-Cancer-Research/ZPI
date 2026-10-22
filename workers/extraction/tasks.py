import tempfile
from functools import cache
from pathlib import Path

from common.storage import BUCKET_REPORTS, download_file
from config.celery import app

from .config import Settings
from .llm import get_llm_client
from .ocr import OcrEngine, get_ocr_engine
from .pipeline import extract_from_images, extract_from_text


@cache
def _settings() -> Settings:
    return Settings.from_env()


@cache
def _ocr() -> OcrEngine:
    settings = _settings()
    return get_ocr_engine(settings.ocr_engine, lang=settings.ocr_lang)


@app.task(name="extraction.run")
def run(keys: list[str], source: str | None = None) -> dict:
    settings = _settings()
    llm = get_llm_client(settings)
    options = {
        "source": source or Path(keys[0]).name,
        "few_shot": settings.few_shot_examples,
        "structured_output": settings.llm_structured_output,
    }
    with tempfile.TemporaryDirectory() as tmp:
        paths = [
            download_file(BUCKET_REPORTS, key, Path(tmp) / f"{i:03d}{Path(key).suffix}")
            for i, key in enumerate(keys)
        ]
        if paths[0].suffix.lower() == ".txt":
            result = extract_from_text(paths[0].read_text(encoding="utf-8"), llm, **options)
        else:
            result = extract_from_images(paths, _ocr(), llm, **options)
    return result.model_dump(mode="json")
