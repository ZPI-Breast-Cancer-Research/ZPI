import shutil
import tempfile
import time
from collections.abc import Sequence
from pathlib import Path

import numpy as np

from .base import ModelInfo, SegmentationError, SegmentationResult

TUMOR_CLASS = 1


class NnUnetModel:
    def __init__(self, model_dir: Path, info: ModelInfo):
        import torch
        from nnunetv2.inference.predict_from_raw_data import nnUNetPredictor

        self.info = info
        options = info.options
        device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

        self._predictor = nnUNetPredictor(
            tile_step_size=options.get("tile_step_size", 0.5),
            use_mirroring=not options.get("disable_tta", False),
            device=device,
        )

        folds = tuple(options.get("folds", [0]))
        try:
            self._predictor.initialize_from_trained_model_folder(str(model_dir), use_folds=folds)
        except FileNotFoundError as error:
            raise SegmentationError(f"Cannot load model from {model_dir}: {error}") from error

    def predict(
        self, channels: Sequence[Path], out_dir: Path, case_id: str
    ) -> SegmentationResult:
        import SimpleITK as sitk

        if len(channels) != len(self.info.channels):
            raise SegmentationError(
                f"Model {self.info.name!r} expects {len(self.info.channels)} channels "
                f"{self.info.channels}, got {len(channels)}"
            )
        for path in channels:
            if not path.exists():
                raise SegmentationError(f"Missing input file: {path}")

        out_dir.mkdir(parents=True, exist_ok=True)
        label_path = out_dir / f"{case_id}.nii.gz"
        probabilities_path = out_dir / f"{case_id}_probabilities.nii.gz"
        start = time.perf_counter()

        with tempfile.TemporaryDirectory(dir=out_dir) as work:
            work_case = Path(work) / case_id
            self._predictor.predict_from_files_sequential(
                [[str(path) for path in channels]],
                [str(work_case)],  # without the file extension
                save_probabilities=True,
            )

            # nnU-Net saves probabilities as (class, z, y, x) with no geometry.
            work_mask = work_case.with_name(f"{case_id}.nii.gz")
            with np.load(work_case.with_name(f"{case_id}.npz")) as saved:
                tumor = saved["probabilities"][TUMOR_CLASS].astype(np.float32)
            image = sitk.GetImageFromArray(tumor)
            image.CopyInformation(sitk.ReadImage(str(work_mask)))
            sitk.WriteImage(image, str(probabilities_path), True)
            shutil.move(work_mask, label_path)

        return SegmentationResult(
            label_path=label_path,
            probabilities_path=probabilities_path,
            model_name=self.info.name,
            model_version=self.info.version,
            seconds=time.perf_counter() - start,
        )
