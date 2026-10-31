from pathlib import Path
from typing import Protocol


class OrientationError(Exception):
    pass


class OrientationDetector(Protocol):
    name: str

    def correction_angle(self, image: Path) -> int: ...


def make_upright(image: Path, detector: OrientationDetector, out_dir: Path) -> tuple[Path, int]:
    """Upright copy of ``image`` in ``out_dir`` and the correction angle that was applied."""
    # Detect on the EXIF-applied copy so detection and rotation see the same pixels.
    upright = upright_copy(image, out_dir)
    angle = detector.correction_angle(upright)
    if angle:
        upright = upright_copy(image, out_dir, angle)
    return upright, angle


def upright_copy(image: Path, out_dir: Path, angle: int = 0) -> Path:
    from PIL import Image, ImageOps

    with Image.open(image) as img:
        img = ImageOps.exif_transpose(img).convert("RGB")
        if angle:
            img = img.rotate(angle, expand=True)
        out = out_dir / f"{image.stem}_{angle}.png"
        img.save(out)
    return out
