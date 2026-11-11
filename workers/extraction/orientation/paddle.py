from pathlib import Path

from .._paddle import import_paddleocr, result_data
from ..errors import OrientationError
from .base import OrientationDetector

MODEL_NAME = "PP-LCNet_x1_0_doc_ori"


class PaddleOrientationDetector(OrientationDetector):
    name = "paddle"

    def __init__(self, model_name: str = MODEL_NAME, enable_mkldnn: bool = False):
        paddleocr = import_paddleocr(OrientationError)
        self._model = paddleocr.DocImgOrientationClassification(
            model_name=model_name, enable_mkldnn=enable_mkldnn
        )

    def correction_angle(self, image: Path) -> int:
        for res in self._model.predict(str(image), batch_size=1):
            return int(result_data(res)["label_names"][0])
        raise OrientationError(f"Orientation model returned no result for {image.name}")
