"""Report text -> image that looks like a phone photo of a printed report.

The page is typeset like the reports of the clinic (serif font, bold underlined "Opis badania:",
a rule under the header), then optionally marked with pen (brackets in the margin, dates and
roman numerals next to the conclusion, as doctors annotate printouts) and photographed: paper
on a squared-paper desk, perspective, slight tilt, uneven light, blur, noise, JPEG.

Everything random comes from one seed, so the same text and options give the same image.
``level`` sets how hard the photo is for OCR: 0 clean scan, 1 decent photo, 2 poor photo.
"""

import json
import math
import random
import zlib
from dataclasses import asdict, dataclass
from functools import cache
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

from ..errors import ExtractionError

# ---- page: A4 at 150 dpi; 25 px is ~12 pt, the size of the printed reports ----
PAGE_WIDTH, PAGE_HEIGHT = 1240, 1754
MARGIN = 120
FONT_SIZE = 25
LINE_HEIGHT = int(FONT_SIZE * 1.4)
INK = (25, 25, 25)
PAPER = (250, 249, 245)
HEADER_END = "Opis badania:"
CROP_ABOVE, CROP_BELOW = 70, 90  # px kept around the report part when the header is cropped


@dataclass(frozen=True)
class PhotoProfile:
    """How a page is turned into an image at one ``level``."""

    desk: bool  # photographed on a desk (False: a flatbed scan, only noise)
    perspective: float  # max inward shift of each corner, share of the image size
    tilt: float  # max rotation, degrees
    shade: float  # darkening by uneven light and vignette, 0-1
    blur: float  # Gaussian blur radius, px (plus up to BLUR_JITTER)
    noise: float  # standard deviation of pixel noise, 0-255 scale
    jpeg: int  # JPEG quality the image is saved with


# Set by eye against the clinic's photos, not tuned on OCR results yet.
PROFILES = {
    0: PhotoProfile(desk=False, perspective=0, tilt=0, shade=0, blur=0, noise=2, jpeg=92),
    1: PhotoProfile(desk=True, perspective=0.025, tilt=1.5, shade=0.12, blur=0.5, noise=6, jpeg=82),
    2: PhotoProfile(desk=True, perspective=0.05, tilt=3.0, shade=0.24, blur=1.0, noise=9, jpeg=62),
}
LEVELS = tuple(PROFILES)
ROTATIONS = (0, 90, 180, 270)
BLUR_JITTER = 0.4

# ---- desk under the photographed page ----
DESK = (236, 237, 240)
GRID = (195, 200, 215)
GRID_STEP = 42
OUTSIDE = (205, 205, 200)  # what the camera sees beyond the desk after tilt and perspective
DESK_PAD = 0.08  # desk visible around the page, share of the page width

# ---- pen marks ----
PENS = ((200, 35, 45), (35, 45, 150))  # red, blue
PEN_ALPHA = 215
PEN_WIDTH = 3
NOTES = ("I", "II", "III", "11.06", "17.06", "24.06")  # appointment numbers and dates
NOTE_SIZE = (34, 44)  # px, font size range of handwritten notes
NOTE_TILT = 12  # degrees
BRACKET_LINES = (2, 4)  # how many lines a margin bracket spans
MAX_NOTED_LINES = 3  # conclusion lines that get a note
CIRCLE_CHANCE = 0.6  # a circled number in the top corner

# ---- random mix of RenderOptions.random: like real uploads ----
LEVEL_WEIGHTS = (2, 5, 3)
ROTATION_WEIGHTS = (14, 3, 1, 2)
MARKS_CHANCE = 0.5
CROP_CHANCE = 0.5


@dataclass(frozen=True)
class RenderOptions:
    level: int = 1
    rotation: int = 0  # degrees counter-clockwise, as a phone held sideways
    marks: bool = False
    # photo of the report part only: the header (patient, diagnosis) is outside the frame
    crop: bool = False
    seed: int = 0

    def __post_init__(self) -> None:
        if self.level not in LEVELS:
            raise ValueError(f"level must be one of {LEVELS}")
        if self.rotation not in ROTATIONS:
            raise ValueError(f"rotation must be one of {ROTATIONS}")

    @classmethod
    def random(cls, seed: int) -> "RenderOptions":
        """A mix like real uploads: mostly decent photos, some sideways, half with pen marks."""
        rng = random.Random(seed)
        return cls(
            level=rng.choices(LEVELS, weights=LEVEL_WEIGHTS)[0],
            rotation=rng.choices(ROTATIONS, weights=ROTATION_WEIGHTS)[0],
            marks=rng.random() < MARKS_CHANCE,
            crop=rng.random() < CROP_CHANCE,
            seed=seed,
        )


class FontNotFoundError(ExtractionError):
    """The DejaVu fonts (shipped with matplotlib) are not installed."""


def render_report(text: str, options: RenderOptions | None = None) -> Image.Image:
    options = options or RenderOptions()
    rng = random.Random(options.seed)
    page, lines = _typeset(text)
    if options.marks:
        _pen_marks(page, lines, rng)
    if options.crop:
        page = _crop_to_report(page, lines)
    image = _photograph(page, PROFILES[options.level], rng)
    if options.rotation:
        image = image.rotate(options.rotation, expand=True)
    return image


def render_directory(
    source: Path, out_dir: Path, *, seed: int = 0, options: RenderOptions | None = None
) -> list[dict]:
    """Render every ``<name>.txt`` in ``source`` to ``out_dir/<name>.jpg``.

    Without ``options`` each report gets ``RenderOptions.random`` from ``seed`` and its name.
    The options and the profile of their level are written to ``out_dir/render.json``, so
    results can be split by level and stay explained after ``PROFILES`` change.
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    manifest = []
    for path in sorted(source.glob("*.txt")):
        report_seed = seed * 1_000_003 + zlib.crc32(path.stem.encode())
        used = options or RenderOptions.random(report_seed)
        image = render_report(path.read_text(encoding="utf-8"), used)
        out = out_dir / f"{path.stem}.jpg"
        profile = PROFILES[used.level]
        image.save(out, quality=profile.jpeg)
        manifest.append({"image": out.name, **asdict(used), "profile": asdict(profile)})
    (out_dir / "render.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return manifest


# ---- page ----------------------------------------------------------------------------------


@dataclass
class _Line:
    text: str
    x: int
    y: int
    width: int
    in_body: bool
    is_conclusion: bool


@cache
def _font(style: str, size: int) -> ImageFont.FreeTypeFont:
    try:
        import matplotlib
    except ImportError as exc:
        raise FontNotFoundError(
            "Rendering needs the DejaVu fonts from matplotlib: pip install matplotlib"
        ) from exc
    path = Path(matplotlib.get_data_path()) / "fonts" / "ttf" / f"DejaVu{style}.ttf"
    return ImageFont.truetype(str(path), size)


def wrap(text: str, font: ImageFont.FreeTypeFont, width: int) -> list[str]:
    """Split one paragraph into lines that fit ``width`` pixels, at spaces."""
    lines: list[str] = []
    current = ""
    for word in text.split(" "):
        candidate = f"{current} {word}" if current else word
        if current and font.getlength(candidate) > width:
            lines.append(current)
            current = word
        else:
            current = candidate
    lines.append(current)
    return lines


def _typeset(text: str) -> tuple[Image.Image, list[_Line]]:
    regular, bold = _font("Serif", FONT_SIZE), _font("Serif-Bold", FONT_SIZE)
    width = PAGE_WIDTH - 2 * MARGIN
    rows: list[tuple[str, ImageFont.FreeTypeFont, bool, bool]] = []
    in_body = False
    for paragraph in text.rstrip("\n").split("\n"):
        stripped = paragraph.strip()
        if stripped.startswith(HEADER_END):
            in_body = True
        if stripped.startswith(("Wykonał", "Opis:")):
            in_body = False
        font = bold if not in_body and ":" in stripped[:20] or stripped == HEADER_END else regular
        for line in wrap(stripped, font, width) if stripped else [""]:
            rows.append((line, font, in_body, stripped.startswith("R.")))

    height = max(PAGE_HEIGHT, 2 * MARGIN + LINE_HEIGHT * (len(rows) + 2))
    page = Image.new("RGB", (PAGE_WIDTH, height), PAPER)
    draw = ImageDraw.Draw(page)
    lines: list[_Line] = []
    y = MARGIN
    conclusion = False
    for line, font, in_body, starts_conclusion in rows:
        conclusion = (conclusion or starts_conclusion) and in_body and bool(line)
        if line == HEADER_END:
            # the rule that separates the header from the report, as on the printouts
            draw.line((MARGIN, y - 12, PAGE_WIDTH - MARGIN, y - 12), fill=INK, width=2)
        if line:
            draw.text((MARGIN, y), line, font=font, fill=INK)
            line_width = int(font.getlength(line))
            if line == HEADER_END:
                draw.line(
                    (MARGIN, y + FONT_SIZE + 3, MARGIN + line_width, y + FONT_SIZE + 3),
                    fill=INK,
                    width=2,
                )
            lines.append(_Line(line, MARGIN, y, line_width, in_body, conclusion))
        y += LINE_HEIGHT
    return page, lines


def _crop_to_report(page: Image.Image, lines: list[_Line]) -> Image.Image:
    """From just above "Opis badania:" to just below the last line, the full page width."""
    start = next((line.y for line in lines if line.text == HEADER_END), MARGIN)
    end = lines[-1].y + LINE_HEIGHT if lines else page.height
    top, bottom = max(0, start - CROP_ABOVE), min(page.height, end + CROP_BELOW)
    return page.crop((0, top, page.width, bottom))


# ---- pen marks -----------------------------------------------------------------------------


def _pen_marks(page: Image.Image, lines: list[_Line], rng: random.Random) -> None:
    """Strokes a doctor adds to a printout: they overlap the text OCR has to read."""
    overlay = Image.new("RGBA", page.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    body = [line for line in lines if line.in_body and line.text != HEADER_END]
    conclusion = [line for line in body if line.is_conclusion]
    pen = (*rng.choice(PENS), PEN_ALPHA)

    if len(body) > 3:  # a bracket in the left margin along a few lines
        start = rng.randrange(0, len(body) - 3)
        end = min(start + rng.randint(*BRACKET_LINES), len(body) - 1)
        top, bottom = body[start].y, body[end].y + 30
        x = MARGIN - rng.randint(18, 40)
        points = [
            (x + rng.uniform(-3, 3) + 6 * math.sin(i / 4), top + i * (bottom - top) / 12)
            for i in range(13)
        ]
        points = [(x + 22, top - 6), *points, (x + 25, bottom + 4)]
        draw.line(points, fill=pen, width=rng.randint(PEN_WIDTH, PEN_WIDTH + 1), joint="curve")

    pen = (*PENS[0], PEN_ALPHA)  # notes next to the conclusion are in red
    script = _font("Sans-Oblique", rng.randint(*NOTE_SIZE))
    for line in conclusion[: rng.randint(1, MAX_NOTED_LINES)]:  # number or date after a line
        dated = f"{rng.randint(1, 28)}.0{rng.randint(1, 9)}"
        note = rng.choice([*NOTES, dated])
        x = min(line.x + line.width + rng.randint(20, 60), PAGE_WIDTH - 140)
        _handwrite(overlay, (x, line.y - 8), note, script, pen, rng)
        draw.line(
            (x - 4, line.y + FONT_SIZE + 6, x + rng.randint(40, 90), line.y + FONT_SIZE + 2),
            fill=pen,
            width=PEN_WIDTH,
        )

    if rng.random() < CIRCLE_CHANCE and lines:  # a circled number in the top corner
        cx, cy = PAGE_WIDTH - MARGIN - rng.randint(0, 60), lines[0].y + rng.randint(10, 60)
        _handwrite(overlay, (cx - 12, cy - 22), str(rng.randint(1, 9)), script, pen, rng)
        draw.ellipse((cx - 32, cy - 30, cx + 38, cy + 34), outline=pen, width=PEN_WIDTH)

    page.paste(Image.alpha_composite(page.convert("RGBA"), overlay).convert("RGB"))


def _handwrite(
    overlay: Image.Image,
    xy: tuple[int, int],
    text: str,
    font: ImageFont.FreeTypeFont,
    pen: tuple[int, int, int, int],
    rng: random.Random,
) -> None:
    """Text in a slanted font, tilted a little, as a quick note by hand."""
    _, _, right, bottom = font.getbbox(text)
    patch = Image.new("RGBA", (right + 10, bottom + 10), (0, 0, 0, 0))
    ImageDraw.Draw(patch).text((5, 5), text, font=font, fill=pen)
    patch = patch.rotate(
        rng.uniform(-NOTE_TILT, NOTE_TILT), expand=True, resample=Image.Resampling.BICUBIC
    )
    overlay.alpha_composite(patch, (max(0, xy[0]), max(0, xy[1])))


# ---- photo ---------------------------------------------------------------------------------


def _photograph(page: Image.Image, profile: PhotoProfile, rng: random.Random) -> Image.Image:
    if not profile.desk:
        return _noise(page, profile.noise, rng)
    pad = int(page.width * DESK_PAD)
    desk = _squared_paper((page.width + 2 * pad, page.height + 2 * pad))
    shift = pad // 3
    desk.paste(page, (pad + rng.randint(-shift, shift), pad + rng.randint(-shift, shift)))
    image = _perspective(desk, profile.perspective, rng)
    image = image.rotate(
        rng.uniform(-profile.tilt, profile.tilt),
        resample=Image.Resampling.BICUBIC,
        fillcolor=OUTSIDE,
    )
    image = _lighting(image, profile.shade, rng)
    image = image.filter(ImageFilter.GaussianBlur(profile.blur + rng.uniform(0, BLUR_JITTER)))
    return _noise(image, profile.noise, rng)


def _squared_paper(size: tuple[int, int]) -> Image.Image:
    desk = Image.new("RGB", size, DESK)
    draw = ImageDraw.Draw(desk)
    for x in range(0, size[0], GRID_STEP):
        draw.line((x, 0, x, size[1]), fill=GRID, width=2)
    for y in range(0, size[1], GRID_STEP):
        draw.line((0, y, size[0], y), fill=GRID, width=2)
    return desk


def _perspective(image: Image.Image, strength: float, rng: random.Random) -> Image.Image:
    """Moves each corner inwards by up to ``strength`` of the size: a photo taken at an angle."""
    import numpy as np

    w, h = image.size
    corners = [(0, 0), (w, 0), (w, h), (0, h)]
    shifted = [
        (
            x + rng.uniform(0, strength) * w * (1 if x == 0 else -1),
            y + rng.uniform(0, strength) * h * (1 if y == 0 else -1),
        )
        for x, y in corners
    ]
    # PIL maps output pixels to input ones: solve for the 8 coefficients of that projection.
    rows, targets = [], []
    for (x, y), (u, v) in zip(shifted, corners, strict=True):
        rows += [[x, y, 1, 0, 0, 0, -u * x, -u * y], [0, 0, 0, x, y, 1, -v * x, -v * y]]
        targets += [u, v]
    coefficients = np.linalg.solve(np.array(rows, float), np.array(targets, float))
    return image.transform(
        image.size,
        Image.Transform.PERSPECTIVE,
        tuple(coefficients),
        Image.Resampling.BICUBIC,
        fillcolor=OUTSIDE,
    )


def _lighting(image: Image.Image, strength: float, rng: random.Random) -> Image.Image:
    """Darker towards one side and the corners: a lamp or a window, and the phone's shadow."""
    import numpy as np

    w, h = image.size
    angle = rng.uniform(0, 2 * math.pi)
    ys, xs = np.mgrid[0:h, 0:w].astype(np.float32)
    ramp = ((xs / w - 0.5) * math.cos(angle) + (ys / h - 0.5) * math.sin(angle)) + 0.5
    vignette = ((xs / w - 0.5) ** 2 + (ys / h - 0.5) ** 2) * 2
    shade = 1 - strength * (ramp + 0.6 * vignette)
    pixels = np.asarray(image, dtype=np.float32) * shade[..., None]
    return Image.fromarray(np.clip(pixels, 0, 255).astype(np.uint8))


def _noise(image: Image.Image, sigma: float, rng: random.Random) -> Image.Image:
    import numpy as np

    generator = np.random.default_rng(rng.randrange(2**32))
    pixels = np.asarray(image, dtype=np.float32)
    pixels += generator.normal(0, sigma, pixels.shape).astype(np.float32)
    return Image.fromarray(np.clip(pixels, 0, 255).astype(np.uint8))
