"""Exercise polarity and narrow-strip handling without downloading OCR models."""

import numpy as np
import pytest
from PIL import Image

from mathcraft_ocr.formula_lines import split_formula_line_groups
from mathcraft_ocr.image import normalize_formula_polarity, prepare_formula_canvas


def formula_strip():
    image = np.full((58, 663, 3), 255, dtype=np.uint8)
    for left, right in ((35, 275), (310, 425), (450, 505), (540, 610)):
        for x in range(left, right - 5, 9):
            image[22:38, x : x + 6] = 0
    image[17:22, 405:410] = 0
    return image


def test_dark_formula_normalization_preserves_pixels_and_geometry():
    expected = formula_strip()
    dark = 255 - expected
    original = dark.copy()
    assert np.array_equal(normalize_formula_polarity(dark), expected)
    assert np.array_equal(dark, original)
    assert normalize_formula_polarity(expected) is expected


@pytest.mark.parametrize("value", [0, 30, 255])
def test_blank_background_is_not_mistaken_for_light_ink(value):
    image = np.full((60, 500, 3), value, dtype=np.uint8)
    assert normalize_formula_polarity(image) is image


def test_dark_border_on_light_page_does_not_invert_text():
    image = formula_strip()
    image[:3] = image[-3:] = 0
    image[:, :3] = image[:, -3:] = 0
    assert normalize_formula_polarity(image) is image


def test_nonuniform_dark_image_is_not_inverted():
    gray = np.tile(np.linspace(0, 160, 300, dtype=np.uint8), (80, 1))
    image = np.repeat(gray[:, :, None], 3, axis=2)
    assert normalize_formula_polarity(image) is image


def test_wide_canvas_adds_whitespace_without_resampling_ink():
    image = formula_strip()
    canvas = np.array(prepare_formula_canvas(255 - image))
    assert canvas.shape[1] == image.shape[1]
    assert canvas.shape[1] <= canvas.shape[0] * 4
    offset = (canvas.shape[0] - image.shape[0]) // 2
    assert np.array_equal(canvas[offset : offset + image.shape[0]], image)
    assert np.all(canvas[:offset] == 255)
    assert np.all(canvas[offset + image.shape[0] :] == 255)


def test_compact_formula_canvas_is_unchanged():
    image = formula_strip()[:, :180]
    assert np.array_equal(
        np.array(prepare_formula_canvas(Image.fromarray(image))), image
    )


@pytest.mark.parametrize("scale", [1, 2])
def test_long_strip_cuts_are_polarity_independent_and_preserve_all_ink(scale):
    image = np.repeat(np.repeat(formula_strip(), scale, axis=0), scale, axis=1)
    light_groups = split_formula_line_groups(image)
    dark_groups = split_formula_line_groups(255 - image)
    assert len(light_groups) == len(dark_groups) == 1
    light_boxes = [crop.box for crop in light_groups[0].crops]
    assert len(light_boxes) >= 2
    assert light_boxes == [crop.box for crop in dark_groups[0].crops]
    covered = np.zeros(image.shape[:2], dtype=bool)
    for left, top, right, bottom in light_boxes:
        covered[top:bottom, left:right] = True
    assert np.all(covered[image[:, :, 0] < 128])


def test_long_single_word_without_safe_whitespace_is_not_cut():
    image = np.full((40, 600, 3), 255, dtype=np.uint8)
    for x in range(12, 580, 9):
        image[12:28, x : x + 7] = 0
    assert split_formula_line_groups(image) == ()
