from typing import Any

from ..plugins import load_class
from .base import OrientationDetector

DETECTORS = {
    "paddle": ".paddle:PaddleOrientationDetector",
}


def get_orientation_detector(name: str, **options: Any) -> OrientationDetector | None:
    if name == "none":
        return None
    cls = load_class(DETECTORS, name, "orientation detector", __package__, extra=("none",))
    return cls(**options)
