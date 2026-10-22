from dataclasses import dataclass, field
from pathlib import Path
from statistics import median
from typing import Protocol

IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".tif", ".tiff", ".bmp"}


class OcrError(Exception):
    pass


@dataclass
class OcrLine:
    text: str
    confidence: float | None = None


@dataclass
class OcrPage:
    source: str
    lines: list[OcrLine] = field(default_factory=list)
    rotation: int | None = None

    @property
    def text(self) -> str:
        return "\n".join(line.text for line in self.lines)


@dataclass
class OcrResult:
    engine: str
    engine_version: str
    pages: list[OcrPage]
    seconds: float
    orientation: str | None = None

    @property
    def text(self) -> str:
        return "\n\n".join(page.text for page in self.pages)

    @property
    def mean_confidence(self) -> float | None:
        scores = [
            line.confidence
            for page in self.pages
            for line in page.lines
            if line.confidence is not None
        ]
        return sum(scores) / len(scores) if scores else None


class OcrEngine(Protocol):
    name: str
    version: str

    def read_page(self, image: Path) -> OcrPage: ...


@dataclass
class _Box:
    text: str
    confidence: float | None
    x_min: float
    y_min: float
    y_max: float

    @property
    def y_center(self) -> float:
        return (self.y_min + self.y_max) / 2


def boxes_to_lines(
    boxes: list[tuple[str, float | None, float, float, float, float]],
) -> list[OcrLine]:
    items = [_Box(t, c, x0, y0, y1) for t, c, x0, y0, _x1, y1 in boxes if t.strip()]
    if not items:
        return []
    tolerance = 0.5 * median(b.y_max - b.y_min for b in items)

    rows: list[list[_Box]] = []
    for box in sorted(items, key=lambda b: b.y_center):
        if rows and abs(box.y_center - _row_center(rows[-1])) <= tolerance:
            rows[-1].append(box)
        else:
            rows.append([box])

    lines = []
    for row in rows:
        row.sort(key=lambda b: b.x_min)
        scores = [b.confidence for b in row if b.confidence is not None]
        lines.append(
            OcrLine(
                text=" ".join(b.text.strip() for b in row),
                confidence=sum(scores) / len(scores) if scores else None,
            )
        )
    return lines


def _row_center(row: list[_Box]) -> float:
    return sum(b.y_center for b in row) / len(row)
