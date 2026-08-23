"""Shared image format and resource limits without integration-layer dependencies."""

from __future__ import annotations


SUPPORTED_IMAGE_EXTENSIONS = ("png", "jpg", "jpeg", "bmp", "gif", "tif", "tiff", "webp")
SUPPORTED_PIL_FORMATS = frozenset(("PNG", "JPEG", "BMP", "GIF", "TIFF", "WEBP"))
DEFAULT_MAX_ENCODED_IMAGE_BYTES = 16 * 1024 * 1024
DEFAULT_MAX_DECODED_IMAGE_PIXELS = 40_000_000
