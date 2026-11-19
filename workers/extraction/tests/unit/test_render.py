import json

import pytest

pytest.importorskip("matplotlib", reason="rendering uses the DejaVu fonts from matplotlib")
pytest.importorskip("numpy")

from workers.extraction.datagen import RenderOptions, render_directory, render_report  # noqa: E402
from workers.extraction.datagen.render import PAGE_HEIGHT, PAGE_WIDTH, _font, wrap  # noqa: E402
from workers.extraction.tests.factories import REPORT  # noqa: E402


def test_same_seed_gives_the_same_image():
    # Arrange
    options = RenderOptions(level=2, marks=True, seed=7)

    # Act
    first, second = render_report(REPORT, options), render_report(REPORT, options)

    # Assert
    assert first.tobytes() == second.tobytes()


def test_another_seed_gives_another_image():
    # Act
    first = render_report(REPORT, RenderOptions(level=1, seed=1))
    second = render_report(REPORT, RenderOptions(level=1, seed=2))

    # Assert
    assert first.tobytes() != second.tobytes()


def test_clean_scan_is_one_a4_page():
    # Act
    image = render_report(REPORT, RenderOptions(level=0))

    # Assert
    assert image.size == (PAGE_WIDTH, PAGE_HEIGHT)


def test_photo_is_larger_than_the_page_because_of_the_desk_around_it():
    # Act
    image = render_report(REPORT, RenderOptions(level=1))

    # Assert
    assert image.width > PAGE_WIDTH and image.height > PAGE_HEIGHT


@pytest.mark.parametrize("rotation", [90, 270])
def test_sideways_photo_is_landscape(rotation):
    # Act
    image = render_report(REPORT, RenderOptions(level=0, rotation=rotation))

    # Assert
    assert image.size == (PAGE_HEIGHT, PAGE_WIDTH)


def test_crop_leaves_out_the_header():
    # Act
    cropped = render_report(REPORT, RenderOptions(level=0, crop=True))

    # Assert: a short report fits well under a page once the header is cut
    assert cropped.width == PAGE_WIDTH
    assert cropped.height < PAGE_HEIGHT


def test_long_report_makes_a_taller_page():
    # Arrange
    long_report = REPORT + "\n".join(f"Linia numer {i} opisu." for i in range(80))

    # Act
    image = render_report(long_report, RenderOptions(level=0))

    # Assert
    assert image.height > PAGE_HEIGHT


def test_wrap_keeps_every_word_and_fits_the_width():
    # Arrange
    font = _font("Serif", 25)
    text = "W badaniu usg w piersi lewej na godz 2-5cm od brodawki owalne ognisko " * 3

    # Act
    lines = wrap(text.strip(), font, 600)

    # Assert
    assert len(lines) > 1
    assert " ".join(lines) == text.strip()
    assert all(font.getlength(line) <= 600 for line in lines[:-1])


def test_options_reject_unknown_level_and_rotation():
    # Act / Assert
    with pytest.raises(ValueError):
        RenderOptions(level=3)
    with pytest.raises(ValueError):
        RenderOptions(rotation=45)


def test_render_directory_writes_images_and_the_options_used(tmp_path):
    # Arrange
    source = tmp_path / "text"
    source.mkdir()
    for name in ("a", "b"):
        (source / f"{name}.txt").write_text(REPORT, encoding="utf-8")

    # Act
    manifest = render_directory(source, tmp_path / "images", seed=3)

    # Assert
    assert sorted(p.name for p in (tmp_path / "images").glob("*.jpg")) == ["a.jpg", "b.jpg"]
    saved = json.loads((tmp_path / "images" / "render.json").read_text(encoding="utf-8"))
    assert saved == manifest
    assert {item["image"] for item in saved} == {"a.jpg", "b.jpg"}
    # each report gets its own seed, so a batch is not one photo repeated
    assert saved[0]["seed"] != saved[1]["seed"]


def test_higher_level_is_a_harder_photo_in_every_respect():
    # Arrange
    from workers.extraction.datagen.render import PROFILES

    # Act
    levels = [PROFILES[level] for level in sorted(PROFILES)]

    # Assert
    for easier, harder in zip(levels, levels[1:], strict=False):
        assert harder.perspective >= easier.perspective
        assert harder.tilt >= easier.tilt
        assert harder.shade >= easier.shade
        assert harder.blur >= easier.blur
        assert harder.noise >= easier.noise
        assert harder.jpeg <= easier.jpeg


def test_render_json_records_the_profile_of_each_level(tmp_path):
    # Arrange
    from workers.extraction.datagen.render import PROFILES

    (tmp_path / "a.txt").write_text(REPORT, encoding="utf-8")

    # Act
    manifest = render_directory(tmp_path, tmp_path / "images", options=RenderOptions(level=2))

    # Assert
    assert manifest[0]["profile"]["jpeg"] == PROFILES[2].jpeg
