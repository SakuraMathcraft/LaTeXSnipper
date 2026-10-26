"""Exercise polarity and narrow-strip handling without downloading OCR models."""

import numpy as np
import pytest
from PIL import Image

from mathcraft_ocr.formula_lines import split_formula_line_groups
from mathcraft_ocr.image import normalize_formula_polarity, prepare_formula_image


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


@pytest.mark.parametrize("width", [180, 663])
@pytest.mark.parametrize("dark", [False, True])
@pytest.mark.parametrize("as_pil", [False, True])
def test_formula_model_input_preserves_normalized_pixels(width, dark, as_pil):
    image = formula_strip()
    image = image[:, :width]
    source = 255 - image if dark else image
    if as_pil:
        source = Image.fromarray(source)
    assert np.array_equal(np.array(prepare_formula_image(source)), image)


@pytest.mark.parametrize("scale", [1, 2])
def test_long_strip_cuts_are_polarity_independent_and_preserve_all_ink(scale):
    image = np.repeat(np.repeat(formula_strip(), scale, axis=0), scale, axis=1)
    light_groups = split_formula_line_groups(image)
    dark_groups = split_formula_line_groups(255 - image)
    assert len(light_groups) == len(dark_groups) == 1
    light_boxes = [crop.box for crop in light_groups[0].crops]
    assert len(light_boxes) >= 2
    assert light_boxes == [crop.box for crop in dark_groups[0].crops]
    for light, dark in zip(light_groups[0].crops, dark_groups[0].crops, strict=True):
        assert np.array_equal(
            np.array(prepare_formula_image(light.image)),
            np.array(prepare_formula_image(dark.image)),
        )
    covered = np.zeros(image.shape[:2], dtype=bool)
    for left, top, right, bottom in light_boxes:
        covered[top:bottom, left:right] = True
    assert np.all(covered[image[:, :, 0] < 128])


def test_long_single_word_without_safe_whitespace_is_not_cut():
    image = np.full((40, 600, 3), 255, dtype=np.uint8)
    for x in range(12, 580, 9):
        image[12:28, x : x + 7] = 0
    assert split_formula_line_groups(image) == ()


@pytest.mark.parametrize("dark", [False, True])
def test_wide_matrix_keeps_all_rows_and_columns_together(dark):
    image = np.full((80, 700, 3), 255, dtype=np.uint8)
    image[12:68, 12:15] = 0
    image[12:68, 685:688] = 0
    for top in (18, 48):
        for left in (50, 180, 310, 440, 570):
            image[top : top + 12, left : left + 20] = 0
    assert split_formula_line_groups(255 - image if dark else image) == ()


def test_dark_formula_whole_line_retry_keeps_normalized_pixels(monkeypatch, tmp_path):
    import mathcraft_ocr.runtime as runtime_mod

    image = formula_strip()
    expected_groups = split_formula_line_groups(image)
    expected_crops = [crop.image for crop in expected_groups[0].crops]
    seen_batches = []
    seen_retries = []

    def recognize_images(images, *_args, **_kwargs):
        seen_batches.append(images)
        return [("x", 0.5) for _ in images]

    def recognize_image(image, *_args, **_kwargs):
        seen_retries.append(image)
        return ("x+y", 0.99)

    monkeypatch.setattr(runtime_mod, "recognize_formula_images", recognize_images)
    monkeypatch.setattr(runtime_mod, "recognize_formula_image", recognize_image)
    runtime = runtime_mod.MathCraftRuntime(auto_download=False)
    result = runtime._recognize_formula_rgb(
        255 - image, None, model_dir=tmp_path, max_new_tokens=256
    )

    assert result == ("x+y", 0.99)
    assert len(seen_batches) == len(seen_retries) == 1
    assert len(seen_batches[0]) == len(expected_crops)
    for actual, expected in zip(seen_batches[0], expected_crops, strict=True):
        assert np.array_equal(actual, expected)
    boxes = [crop.box for crop in expected_groups[0].crops]
    left = min(box[0] for box in boxes)
    top = min(box[1] for box in boxes)
    right = max(box[2] for box in boxes)
    bottom = max(box[3] for box in boxes)
    assert np.array_equal(seen_retries[0], image[top:bottom, left:right])


@pytest.mark.parametrize("dark", [False, True])
def test_mixed_detectors_share_normalized_image(monkeypatch, tmp_path, dark):
    from types import SimpleNamespace

    import mathcraft_ocr.runtime as runtime_mod

    image = np.full((40, 200, 3), 255, dtype=np.uint8)
    image[10:25, 10:20] = (30, 60, 90)
    plan = SimpleNamespace(
        ready=True,
        provider_info=SimpleNamespace(active_provider="CPUExecutionProvider"),
        model_dirs={
            model_id: tmp_path for model_id in runtime_mod.PROFILE_MODEL_IDS["mixed"]
        },
    )
    seen = []

    def detect_formulas(rgb, *_args):
        seen.append("formula")
        assert np.array_equal(rgb, image)
        return ()

    def detect_text(bgr, *_args):
        seen.append("text")
        assert np.array_equal(bgr, image[:, :, ::-1])
        return np.array([[[8, 8], [180, 8], [180, 30], [8, 30]]]), (0.99,)

    monkeypatch.setattr(
        runtime_mod.MathCraftRuntime, "_warmup_selected_models", lambda *_args: plan
    )
    monkeypatch.setattr(
        runtime_mod.MathCraftRuntime, "_rec_batch_num", lambda *_args: 1
    )
    monkeypatch.setattr(runtime_mod, "detect_formula_boxes", detect_formulas)
    monkeypatch.setattr(runtime_mod, "detect_text_boxes", detect_text)
    monkeypatch.setattr(
        runtime_mod,
        "recognize_pp_text_lines",
        lambda *_args, **_kwargs: [("text", 0.99)],
    )
    runtime = runtime_mod.MathCraftRuntime(auto_download=False)
    result = runtime.recognize_mixed(255 - image if dark else image)
    assert result.text == "text"
    assert seen == ["formula", "text"]
