from importlib import import_module
from typing import Any

from .base import OcrEngine

ENGINES = {
    "paddle": ".paddle:PaddleOcrEngine",
}


def get_ocr_engine(name: str, **options: Any) -> OcrEngine:
    try:
        target = ENGINES[name]
    except KeyError:
        raise ValueError(f"Unknown OCR engine {name!r}; available: {', '.join(ENGINES)}") from None
    module_name, class_name = target.split(":")
    cls = getattr(import_module(module_name, __package__), class_name)
    return cls(**options)
