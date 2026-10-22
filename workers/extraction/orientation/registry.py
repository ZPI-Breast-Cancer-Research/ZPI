from importlib import import_module
from typing import Any

from .base import OrientationDetector

DETECTORS = {
    "paddle": ".paddle:PaddleOrientationDetector",
}


def get_orientation_detector(name: str, **options: Any) -> OrientationDetector | None:
    if name == "none":
        return None
    try:
        target = DETECTORS[name]
    except KeyError:
        available = ", ".join(["none", *DETECTORS])
        raise ValueError(f"Unknown orientation detector {name!r}; available: {available}") from None
    module_name, class_name = target.split(":")
    cls = getattr(import_module(module_name, __package__), class_name)
    return cls(**options)
