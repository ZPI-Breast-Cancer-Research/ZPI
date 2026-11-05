from importlib import import_module
from pathlib import Path

from .base import SegmentationError, SegmentationModel, read_model_info

ADAPTERS = {
    "nnunet": ".nnunet:NnUnetModel",
}


def get_segmentation_model(model_dir: Path) -> SegmentationModel:
    info = read_model_info(model_dir)

    target = ADAPTERS.get(info.backend)
    if target is None:
        available = ", ".join(ADAPTERS)
        raise SegmentationError(f"Unknown backend {info.backend!r}; available: {available}")

    module_name, class_name = target.split(":")
    module = import_module(module_name, __package__)
    model_class = getattr(module, class_name)
    return model_class(model_dir, info)
