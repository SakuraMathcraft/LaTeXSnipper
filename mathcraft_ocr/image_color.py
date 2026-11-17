"""Pillow-only color normalization shared by the desktop and OCR runtimes."""

from collections import Counter

from PIL import Image


def to_ocr_rgb(image: Image.Image) -> Image.Image:
    """Composite transparency over the opaque edge color or a white canvas."""
    if not image.has_transparency_data or not image.width or not image.height:
        return image if image.mode == "RGB" else image.convert("RGB")

    rgba = image if image.mode == "RGBA" else image.convert("RGBA")
    alpha = rgba.getchannel("A")
    if alpha.getextrema() == (255, 255):
        return rgba.convert("RGB")

    background = Image.new("RGB", rgba.size, _edge_background(rgba))
    background.paste(rgba, mask=alpha)
    return background


def _edge_background(rgba: Image.Image) -> tuple[int, ...]:
    right, bottom = rgba.width - 1, rgba.height - 1
    # Sample the perimeter so a transparent corner cannot set the background.
    samples = []
    for index in range(1, 16):
        x, y = index * right // 16, index * bottom // 16
        samples.extend(
            (
                rgba.getpixel((x, 0)),
                rgba.getpixel((x, bottom)),
                rgba.getpixel((0, y)),
                rgba.getpixel((right, y)),
            )
        )
    colors = Counter(
        pixel[:3] for pixel in samples if isinstance(pixel, tuple) and pixel[3] == 255
    )
    if colors:
        color, count = colors.most_common(1)[0]
        if count * 2 > len(samples):
            return color
    return (255, 255, 255)
