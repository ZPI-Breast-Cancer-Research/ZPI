"""Measurements of a predicted mask, computed once by the worker and shown by the review screens.

- volume_ml: every voxel of the mask (1 ml = 1 cm³).
- largest_volume_ml: the same for the largest connected region only.
- dimensions_mm: extent of the largest connected region along the three image axes, longest first.
  The largest region stands for the lesion, so small false regions elsewhere do not stretch it.
"""

import nibabel as nib
import numpy as np
from scipy import ndimage


def measure(mask: np.ndarray, affine: np.ndarray) -> dict:
    """Volume and dimensions of a mask; an empty mask has volume 0 and no dimensions."""
    mask = np.asarray(mask) > 0
    spacing = nib.affines.voxel_sizes(affine)
    volume_ml = float(mask.sum() * np.prod(spacing) / 1000)
    if not mask.any():
        return {"volume_ml": 0.0, "largest_volume_ml": 0.0, "dimensions_mm": None}

    labels, count = ndimage.label(mask)
    sizes = np.bincount(labels.ravel())[1:]
    voxel_ml = float(np.prod(spacing) / 1000)
    largest = np.argwhere(labels == int(np.argmax(sizes)) + 1)
    extent = (largest.max(axis=0) - largest.min(axis=0) + 1) * spacing
    dimensions = sorted((round(float(d), 1) for d in extent), reverse=True)
    return {
        "volume_ml": round(volume_ml, 2),
        "largest_volume_ml": round(float(sizes.max()) * voxel_ml, 2),
        "dimensions_mm": dimensions,
    }


def measure_file(path) -> dict:
    image = nib.load(path)
    return measure(np.asanyarray(image.dataobj), image.affine)
