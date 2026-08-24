from __future__ import annotations

import io
from pathlib import Path

import pytest
from PIL import Image
from PyQt6.QtGui import QImage

import recognition.image_input as image_input_module
from recognition.image_contracts import DEFAULT_MAX_ENCODED_IMAGE_BYTES
from recognition.image_input import (
    ImageInputError,
    image_from_bytes,
    image_from_path,
    image_from_pil,
    image_from_qimage,
    image_from_stream,
    validated_rgb_image,
)


@pytest.mark.parametrize("encoding", ["PNG", "JPEG", "BMP", "GIF", "TIFF", "WEBP"])
def test_supported_encoded_images_are_normalized_to_rgb(encoding: str) -> None:
    source = Image.new("RGBA", (20, 10), (1, 2, 3, 120))
    if encoding == "JPEG":
        source = source.convert("RGB")
    buffer = io.BytesIO()
    source.save(buffer, format=encoding)

    image = image_from_bytes(buffer.getvalue())

    assert image.mode == "RGB"
    assert image.size == (20, 10)


def test_content_detection_ignores_filename_and_mime() -> None:
    buffer = io.BytesIO()
    Image.new("RGB", (4, 5), "white").save(buffer, format="PNG")
    assert image_from_bytes(buffer.getvalue()).size == (4, 5)


def test_animated_and_multipage_inputs_use_first_frame() -> None:
    first = Image.new("RGB", (4, 4), "red")
    second = Image.new("RGB", (4, 4), "blue")
    buffer = io.BytesIO()
    first.save(buffer, format="GIF", save_all=True, append_images=[second])
    image = image_from_bytes(buffer.getvalue())
    assert image.getpixel((0, 0))[0] > image.getpixel((0, 0))[2]


@pytest.mark.parametrize("encoding", ["GIF", "TIFF", "WEBP"])
def test_multiframe_inputs_use_first_frame(encoding: str) -> None:
    first = Image.new("RGB", (5, 3), "red")
    second = Image.new("RGB", (5, 3), "blue")
    buffer = io.BytesIO()
    first.save(buffer, format=encoding, save_all=True, append_images=[second])
    image = image_from_bytes(buffer.getvalue())
    assert image.getpixel((0, 0))[0] > image.getpixel((0, 0))[2]


def test_exif_orientation_is_applied() -> None:
    source = Image.new("RGB", (9, 4), "white")
    exif = source.getexif()
    exif[274] = 6
    buffer = io.BytesIO()
    source.save(buffer, format="JPEG", exif=exif)
    assert image_from_bytes(buffer.getvalue()).size == (4, 9)


@pytest.mark.parametrize("mode", ["RGB", "RGBA", "L", "P"])
def test_common_color_modes_normalize_to_rgb(mode: str) -> None:
    source = Image.new(mode, (7, 6))
    assert image_from_pil(source).mode == "RGB"


def test_path_stream_bytes_and_pil_are_consistent(tmp_path: Path) -> None:
    source = Image.new("RGBA", (11, 7), (20, 40, 60, 128))
    buffer = io.BytesIO()
    source.save(buffer, format="PNG")
    encoded = buffer.getvalue()
    path = tmp_path / "mismatch.txt"
    path.write_bytes(encoded)

    images = (
        image_from_bytes(encoded),
        image_from_stream(io.BytesIO(encoded)),
        image_from_path(path),
        image_from_pil(source),
    )
    assert {image.mode for image in images} == {"RGB"}
    assert {image.size for image in images} == {(11, 7)}
    assert len({image.tobytes() for image in images}) == 1


def test_corrupt_empty_and_oversized_inputs_have_stable_errors() -> None:
    for data, expected in ((b"", "empty_image"), (b"not an image", "corrupt_image")):
        with pytest.raises(ImageInputError) as raised:
            image_from_bytes(data)
        assert raised.value.code == expected
        assert any("\u4e00" <= char <= "\u9fff" for char in str(raised.value))
    with pytest.raises(ImageInputError) as raised:
        image_from_pil(Image.new("RGB", (20, 20)), max_pixels=399)
    assert raised.value.code == "image_too_large"
    assert any("\u4e00" <= char <= "\u9fff" for char in str(raised.value))


def test_common_input_boundary_preserves_backend_independent_resolution() -> None:
    image = image_from_pil(Image.new("RGB", (5000, 2000)))
    assert image.size == (5000, 2000)


def test_trusted_local_file_is_not_limited_by_remote_upload_bytes(tmp_path: Path) -> None:
    path = tmp_path / "large-local.bmp"
    Image.new("RGB", (2500, 2300), "white").save(path, format="BMP")
    assert path.stat().st_size > DEFAULT_MAX_ENCODED_IMAGE_BYTES

    image = image_from_path(path)

    assert image.size == (2500, 2300)


def test_trusted_rgb_boundary_validates_without_copying_pixels() -> None:
    image = Image.new("RGB", (3000, 100))
    assert validated_rgb_image(image) is image
    with pytest.raises(ImageInputError):
        validated_rgb_image(Image.new("RGBA", (2, 2)))


def test_qimage_conversion_keeps_png_fallback_for_uncommon_layouts(monkeypatch) -> None:
    source = QImage(7, 5, QImage.Format.Format_ARGB32)
    source.fill(0xFF123456)
    monkeypatch.setattr(
        image_input_module,
        "qimage_to_rgb_pil",
        lambda _image: (_ for _ in ()).throw(RuntimeError("unsupported layout")),
    )

    converted = image_from_qimage(source)

    assert converted.mode == "RGB"
    assert converted.size == (7, 5)
