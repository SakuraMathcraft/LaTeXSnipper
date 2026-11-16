"""Render the ribbon icons from Fluent UI System Icons.

Office web add-ins cannot use the ``imageMso`` icons of the Windows ribbon, so
each command uses the Fluent UI System Icon closest to its Windows icon. The
regular-style SVG sources (MIT, see ``fluent-icons/LICENSE``) are rendered to
the 16, 32 and 80 px PNGs the manifest needs, each from the design size
closest to the target. Needs ``rsvg-convert`` (Homebrew ``librsvg``)::

    python Office_plugin/macos/tools/generate_icons.py
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

HERE = Path(__file__).resolve().parent
SOURCES = HERE / "fluent-icons"
OUTPUT = HERE.parent / "web/icons"
SIZES = (16, 32, 80)
INK = "#323130"

# Ribbon icon -> Fluent icon (Windows imageMso it stands in for).
ICONS = {
    "insert-inline": "math_format_linear",  # EquationProfessional
    "insert-display": "math_format_professional",  # EquationInsertGallery
    "insert-numbered": "text_number_list_ltr",  # Numbering
    "insert-formula": "math_formula",  # EquationProfessional (PowerPoint)
    "ocr": "screenshot",  # ScreenshotInsertGallery
    "load": "edit",  # ReviewDisplayForReview
    "delete": "delete",  # Delete
    "parse-selected": "braces_variable",  # SelectionToMathConvert
    "parse-all": "document_search",  # FileDocumentInspect
    "reference": "link",  # CrossReferenceInsert
    "add-number": "number_symbol",  # NumberingRestart
    "renumber": "arrow_sync",  # RecurrenceEdit
    "chapter": "bookmark_add",  # BookmarkInsert
    "section": "document_page_break",  # BreaksGallery
    "format": "paint_brush",  # FormatPainter
    "format-all": "text_font",  # FontDialog
    "to-png": "image",  # PictureInsertFromFile
    "to-svg": "shapes",  # (Mac only)
    "pane": "panel_right",  # ReviewingPane
    "settings": "settings",  # AdvancedFileProperties
    "help": "question_circle",  # Help
}


def design_sizes(name: str) -> list[int]:
    pattern = re.compile(rf"{re.escape(name)}_(\d+)_regular\.svg")
    sizes = [
        int(match.group(1))
        for path in SOURCES.iterdir()
        if (match := pattern.fullmatch(path.name))
    ]
    if not sizes:
        raise FileNotFoundError(f"no Fluent source for {name}")
    return sorted(sizes)


def closest(sizes: list[int], target: int) -> int:
    """The smallest design size at least as large as the target, else the largest."""

    return next((size for size in sizes if size >= min(target, 48)), sizes[-1])


def render(name: str, size: int, output: Path) -> None:
    source = SOURCES / f"{name}_{closest(design_sizes(name), size)}_regular.svg"
    svg = source.read_text(encoding="utf-8").replace("<svg ", f'<svg fill="{INK}" ', 1)
    subprocess.run(
        [
            "rsvg-convert",
            "--width",
            str(size),
            "--height",
            str(size),
            "--format",
            "png",
            "--output",
            str(output),
        ],
        input=svg.encode("utf-8"),
        check=True,
    )


def main() -> None:
    OUTPUT.mkdir(parents=True, exist_ok=True)
    for icon, name in ICONS.items():
        for size in SIZES:
            render(name, size, OUTPUT / f"{icon}-{size}.png")


if __name__ == "__main__":
    main()
