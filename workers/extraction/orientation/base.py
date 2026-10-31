from pathlib import Path
from typing import Protocol


class OrientationError(Exception):
    pass


class OrientationDetector(Protocol):
    name: str

    def correction_angle(self, image: Path) -> int: ...


def upright_copy(image: Path, out_dir: Path, angle: int = 0) -> Path:
    from PIL import Image, ImageOps

    with Image.open(image) as img:
        img = ImageOps.exif_transpose(img).convert("RGB")
        if angle:
            img = img.rotate(angle, expand=True)
        out = out_dir / f"{image.stem}_{angle}.png"
        img.save(out)
    return out
