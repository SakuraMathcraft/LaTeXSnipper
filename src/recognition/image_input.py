"""The sole safe image decoding and common RGB normalization boundary."""

from __future__ import annotations

import io
import warnings
from pathlib import Path
from typing import BinaryIO

from PIL import Image, ImageOps, UnidentifiedImageError

from recognition.image_contracts import (
    DEFAULT_MAX_DECODED_IMAGE_PIXELS,
    DEFAULT_MAX_ENCODED_IMAGE_BYTES,
    SUPPORTED_PIL_FORMATS,
)
from recognition.image_preprocess import qimage_to_rgb_pil


class ImageInputError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.user_message = message


def _validate_size(image: Image.Image, *, max_pixels: int) -> None:
    width, height = image.size
    if width <= 0 or height <= 0:
        raise ImageInputError("empty_image", "图片内容为空。")
    if width * height > max_pixels:
        raise ImageInputError("image_too_large", "图片尺寸超过安全限制。")


def _normalize_open_image(image: Image.Image, *, max_pixels: int) -> Image.Image:
    actual_format = str(image.format or "").upper()
    if actual_format not in SUPPORTED_PIL_FORMATS:
        raise ImageInputError("unsupported_image_format", "不支持该图片编码格式。")
    _validate_size(image, max_pixels=max_pixels)
    try:
        image.seek(0)
        oriented = ImageOps.exif_transpose(image)
        _validate_size(oriented, max_pixels=max_pixels)
        oriented.load()
        rgb = oriented.convert("RGB")
    except Image.DecompressionBombError as exc:
        raise ImageInputError("image_too_large", "图片尺寸超过安全解码限制。") from exc
    except (OSError, SyntaxError, ValueError) as exc:
        raise ImageInputError("corrupt_image", "图片数据已损坏或不完整。") from exc
    rgb.load()
    return rgb


def image_from_bytes(
    data: bytes,
    *,
    max_encoded_bytes: int = DEFAULT_MAX_ENCODED_IMAGE_BYTES,
    max_pixels: int = DEFAULT_MAX_DECODED_IMAGE_PIXELS,
) -> Image.Image:
    if not data:
        raise ImageInputError("empty_image", "图片内容为空。")
    if len(data) > max_encoded_bytes:
        raise ImageInputError("image_too_large", "图片文件超过大小限制。")
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(data)) as image:
                return _normalize_open_image(image, max_pixels=max_pixels)
    except ImageInputError:
        raise
    except (Image.DecompressionBombError, Image.DecompressionBombWarning) as exc:
        raise ImageInputError("image_too_large", "图片尺寸超过安全解码限制。") from exc
    except (UnidentifiedImageError, OSError, SyntaxError, ValueError) as exc:
        raise ImageInputError("corrupt_image", "图片数据已损坏或格式不受支持。") from exc


def image_from_stream(stream: BinaryIO, **kwargs) -> Image.Image:
    max_encoded = int(kwargs.get("max_encoded_bytes", DEFAULT_MAX_ENCODED_IMAGE_BYTES))
    max_pixels = int(kwargs.get("max_pixels", DEFAULT_MAX_DECODED_IMAGE_PIXELS))
    try:
        start = stream.tell()
        stream.seek(0, io.SEEK_END)
        size = stream.tell() - start
        stream.seek(start)
    except (AttributeError, OSError):
        return image_from_bytes(stream.read(max_encoded + 1), **kwargs)
    if size <= 0:
        raise ImageInputError("empty_image", "图片内容为空。")
    if size > max_encoded:
        raise ImageInputError("image_too_large", "图片文件超过大小限制。")
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(stream) as image:
                return _normalize_open_image(image, max_pixels=max_pixels)
    except ImageInputError:
        raise
    except (Image.DecompressionBombError, Image.DecompressionBombWarning) as exc:
        raise ImageInputError("image_too_large", "图片尺寸超过安全解码限制。") from exc
    except (UnidentifiedImageError, OSError, SyntaxError, ValueError) as exc:
        raise ImageInputError("corrupt_image", "图片数据已损坏或格式不受支持。") from exc


def image_from_path(
    path: str | Path,
    *,
    max_encoded_bytes: int | None = None,
    max_pixels: int = DEFAULT_MAX_DECODED_IMAGE_PIXELS,
) -> Image.Image:
    """Decode a trusted local file without applying the remote upload byte limit."""
    source = Path(path)
    try:
        size = source.stat().st_size
    except OSError as exc:
        raise ImageInputError("corrupt_image", "无法读取图片文件。") from exc
    if max_encoded_bytes is not None and size > int(max_encoded_bytes):
        raise ImageInputError("image_too_large", "图片文件超过大小限制。")
    try:
        with source.open("rb") as stream:
            return image_from_stream(
                stream,
                max_encoded_bytes=int(max_encoded_bytes) if max_encoded_bytes is not None else max(1, size),
                max_pixels=max_pixels,
            )
    except OSError as exc:
        raise ImageInputError("corrupt_image", "无法读取图片文件。") from exc


def image_from_pil(
    image: Image.Image,
    *,
    max_pixels: int = DEFAULT_MAX_DECODED_IMAGE_PIXELS,
) -> Image.Image:
    _validate_size(image, max_pixels=max_pixels)
    try:
        copy = ImageOps.exif_transpose(image).convert("RGB")
        copy.load()
    except (OSError, SyntaxError, ValueError) as exc:
        raise ImageInputError("corrupt_image", "图片数据已损坏或不完整。") from exc
    return copy


def validated_rgb_image(
    image: Image.Image,
    *,
    max_pixels: int = DEFAULT_MAX_DECODED_IMAGE_PIXELS,
) -> Image.Image:
    """Validate a freshly-created trusted RGB image without an avoidable full copy."""
    _validate_size(image, max_pixels=max_pixels)
    if image.mode != "RGB":
        raise ImageInputError("corrupt_image", "内部图片必须为 RGB 格式。")
    try:
        image.load()
    except (OSError, SyntaxError, ValueError) as exc:
        raise ImageInputError("corrupt_image", "图片数据已损坏或不完整。") from exc
    return image


def image_from_qimage(image, *, max_pixels: int = DEFAULT_MAX_DECODED_IMAGE_PIXELS) -> Image.Image:
    if image is None or image.isNull():
        raise ImageInputError("empty_image", "图片内容为空。")
    try:
        converted = qimage_to_rgb_pil(image)
    except Exception:
        converted = _qimage_via_png(image, max_pixels=max_pixels)
    return validated_rgb_image(converted, max_pixels=max_pixels)


def _qimage_via_png(image, *, max_pixels: int) -> Image.Image:
    """Retain a portable fallback for uncommon Qt image layouts."""
    from PyQt6.QtCore import QBuffer, QIODevice

    buffer = QBuffer()
    if not buffer.open(QIODevice.OpenModeFlag.ReadWrite) or not image.save(buffer, "PNG"):
        raise ImageInputError("corrupt_image", "无法读取 Qt 图片数据。")
    try:
        encoded = bytes(buffer.data())
        return image_from_bytes(
            encoded,
            max_encoded_bytes=max(1, len(encoded)),
            max_pixels=max_pixels,
        )
    finally:
        buffer.close()


def image_from_qpixmap(pixmap, *, max_pixels: int = DEFAULT_MAX_DECODED_IMAGE_PIXELS) -> Image.Image:
    if pixmap is None or pixmap.isNull():
        raise ImageInputError("empty_image", "图片内容为空。")
    return image_from_qimage(pixmap.toImage(), max_pixels=max_pixels)
