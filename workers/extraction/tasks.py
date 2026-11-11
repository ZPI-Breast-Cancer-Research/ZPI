import tempfile
from functools import cache
from pathlib import Path

from common.storage import BUCKET_REPORTS, download_file
from config.celery import app

from .config import Settings
from .documents import Document
from .pipeline import Extractor


@cache
def _extractor() -> Extractor:
    # One per worker process: loading the OCR models takes a while.
    return Extractor.from_settings(Settings.from_env())


@app.task(name="extraction.run")
def run(keys: list[str], extraction_id: int | None = None, source: str | None = None) -> dict:
    # extraction_id: the backend ExtractionResult row; saving the result there is not wired up yet.
    with tempfile.TemporaryDirectory() as tmp:
        paths = [
            download_file(BUCKET_REPORTS, key, Path(tmp) / f"{i:03d}{Path(key).suffix}")
            for i, key in enumerate(keys)
        ]
        document = Document(source or Path(keys[0]).name, paths)
        result = _extractor().extract(document)
    return result.model_dump(mode="json")
