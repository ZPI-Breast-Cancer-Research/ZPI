import os
from pathlib import Path
from typing import Any

from ..ocr.base import OcrError

MODEL_NAME = "PP-LCNet_x1_0_doc_ori"


class PaddleOrientationDetector:
    name = "paddle"

    def __init__(self, model_name: str = MODEL_NAME, enable_mkldnn: bool = False):
        os.environ.setdefault("PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK", "True")
        try:
            from paddleocr import DocImgOrientationClassification
        except ImportError as exc:
            raise OcrError(
                "PaddleOCR is not installed: pip install -r requirements-paddle.txt"
            ) from exc
        self._model = DocImgOrientationClassification(
            model_name=model_name, enable_mkldnn=enable_mkldnn
        )

    def correction_angle(self, image: Path) -> int:
        for res in self._model.predict(str(image), batch_size=1):
            data: Any = res.json.get("res", res.json) if hasattr(res, "json") else res
            return int(data["label_names"][0])
        raise OcrError(f"Orientation model returned no result for {image.name}")
