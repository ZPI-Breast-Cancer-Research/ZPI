from typing import Any

from ..plugins import load_class
from .base import OcrEngine

ENGINES = {
    "paddle": ".paddle:PaddleOcrEngine",
}


def get_ocr_engine(name: str, **options: Any) -> OcrEngine:
    return load_class(ENGINES, name, "OCR engine", __package__)(**options)
