import json
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

REQUIRED_FIELDS = ("backend", "name", "version", "channels")


class SegmentationError(Exception):
    pass


@dataclass(frozen=True)
class SegmentationResult:
    label_path: Path
    probabilities_path: Path
    model_name: str
    model_version: str
    seconds: float


@dataclass(frozen=True)
class ModelInfo:
    backend: str
    name: str
    version: str
    channels: tuple[str, ...]
    options: dict[str, Any]


class SegmentationModel(Protocol):
    info: ModelInfo

    def predict(
        self, channels: Sequence[Path], out_dir: Path, case_id: str
    ) -> SegmentationResult: ...


def read_model_info(model_dir: Path) -> ModelInfo:
    path = model_dir / "model.json"
    if not path.exists():
        raise SegmentationError(f"Missing {path}")

    try:
        with path.open(encoding="utf-8") as model_file:
            spec = json.load(model_file)
    except json.JSONDecodeError as error:
        raise SegmentationError(f"Invalid JSON in {path}: {error}") from error

    for field in REQUIRED_FIELDS:
        if field not in spec:
            raise SegmentationError(f"Missing field {field!r} in {path}")

    return ModelInfo(
        backend=spec["backend"],
        name=spec["name"],
        version=str(spec["version"]),
        channels=tuple(spec["channels"]),
        options=spec.get("options", {}),
    )
