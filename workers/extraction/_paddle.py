"""PaddleOCR helpers shared by the OCR engine and the orientation detector."""

import os
from types import ModuleType
from typing import Any

from .errors import ExtractionError


def import_paddleocr(error: type[ExtractionError]) -> ModuleType:
    """Import ``paddleocr`` lazily, so the rest of the module works without it installed."""
    os.environ.setdefault("PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK", "True")
    try:
        import paddleocr
    except ImportError as exc:
        raise error("PaddleOCR is not installed: pip install -r requirements-paddle.txt") from exc
    return paddleocr


def result_data(result: Any) -> Any:
    """The prediction dict of a PaddleX result object (or the plain dict of older versions)."""
    return result.json.get("res", result.json) if hasattr(result, "json") else result
