from pathlib import Path
from typing import Any

from .base import OcrError, OcrPage, boxes_to_lines


class PaddleOcrEngine:
    name = "paddle"

    def __init__(
        self,
        lang: str = "pl",
        *,
        unwarp: bool = False,
        detect_orientation: bool = False,
    ):
        try:
            import paddleocr
        except ImportError as exc:
            raise OcrError(
                "PaddleOCR is not installed: pip install -r requirements-paddle.txt"
            ) from exc

        self.version = getattr(paddleocr, "__version__", "unknown")
        try:
            self._ocr = paddleocr.PaddleOCR(
                lang=lang,
                use_doc_orientation_classify=detect_orientation,
                use_doc_unwarping=unwarp,
                use_textline_orientation=detect_orientation,
            )
        except (TypeError, ValueError):
            self._ocr = paddleocr.PaddleOCR(lang=lang, use_angle_cls=detect_orientation)
        self._v3 = hasattr(self._ocr, "predict")

    def read_page(self, image: Path) -> OcrPage:
        boxes = self._read_v3(image) if self._v3 else self._read_v2(image)
        return OcrPage(source=image.name, lines=boxes_to_lines(boxes))

    def _read_v3(self, image: Path) -> list[tuple[str, float | None, float, float, float, float]]:
        boxes = []
        for res in self._ocr.predict(str(image)):
            data: Any = res.json.get("res", res.json) if hasattr(res, "json") else res
            texts = data["rec_texts"]
            scores = data["rec_scores"]
            for text, score, poly in zip(texts, scores, data["rec_polys"], strict=True):
                boxes.append((text, float(score), *_poly_bounds(poly)))
        return boxes

    def _read_v2(self, image: Path) -> list[tuple[str, float | None, float, float, float, float]]:
        boxes = []
        for page in self._ocr.ocr(str(image), cls=True) or []:
            for poly, (text, score) in page or []:
                boxes.append((text, float(score), *_poly_bounds(poly)))
        return boxes


def _poly_bounds(poly: Any) -> tuple[float, float, float, float]:
    xs = [float(point[0]) for point in poly]
    ys = [float(point[1]) for point in poly]
    return min(xs), min(ys), max(xs), max(ys)
