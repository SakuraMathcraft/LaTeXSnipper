"""Formula export format registry and conversion dispatcher."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from preview.math_preview import (
    _latex_display,
    _latex_equation,
    _latex_inline,
    _mathml_to_html_fragment,
    _mathml_with_prefix,
    _normalize_latex_for_export,
)


@dataclass(frozen=True)
class ExportFormatSpec:
    key: str
    label: str | None = None
    separator_before: bool = False


EXPORT_FORMAT_SPECS: tuple[ExportFormatSpec, ...] = (
    ExportFormatSpec("latex", "LaTeX (行内 $...$)"),
    ExportFormatSpec("latex_display", "LaTeX (display \\[...\\])"),
    ExportFormatSpec("latex_equation", "LaTeX (equation 编号)"),
    ExportFormatSpec("", separator_before=True),
    ExportFormatSpec("markdown_inline", "Markdown (行内 $...$)"),
    ExportFormatSpec("markdown_block", "Markdown (块级 $$...$$)"),
    ExportFormatSpec("", separator_before=True),
    ExportFormatSpec("mathml", "MathML"),
    ExportFormatSpec("mathml_mml", "MathML (.mml)"),
    ExportFormatSpec("mathml_m", "MathML (<m>)"),
    ExportFormatSpec("mathml_attr", "MathML (attr)"),
    ExportFormatSpec("", separator_before=True),
    ExportFormatSpec("html", "HTML"),
    ExportFormatSpec("omml", "Word OMML"),
    ExportFormatSpec("svgcode", "SVG Code"),
)

FORMAT_DISPLAY_NAMES = {
    "latex": "LaTeX (行内)",
    "latex_display": "LaTeX (display \\[\\])",
    "latex_equation": "LaTeX (equation)",
    "markdown_inline": "Markdown 行内",
    "markdown_block": "Markdown 块级",
    "mathml": "MathML",
    "mathml_mml": "MathML (.mml)",
    "mathml_m": "MathML (<m>)",
    "mathml_attr": "MathML (attr)",
    "html": "HTML",
    "omml": "Word OMML",
    "svgcode": "SVG Code",
}


def build_formula_export(
    format_type: str,
    latex: str,
    *,
    mathml_converter: Callable[[str], str],
    omml_converter: Callable[[str], str],
    svg_converter: Callable[[str], str],
) -> tuple[str, str]:
    """Return (export_text, display_name) for a formula export format."""
    clean = _normalize_latex_for_export(latex)
    fmt = str(format_type or "").strip()

    if fmt == "latex":
        return _latex_inline(clean), FORMAT_DISPLAY_NAMES[fmt]
    if fmt == "latex_display":
        return _latex_display(clean), FORMAT_DISPLAY_NAMES[fmt]
    if fmt == "latex_equation":
        return _latex_equation(clean), FORMAT_DISPLAY_NAMES[fmt]
    if fmt == "markdown_inline":
        return _latex_inline(clean), FORMAT_DISPLAY_NAMES[fmt]
    if fmt == "markdown_block":
        return f"$$\n{clean}\n$$", FORMAT_DISPLAY_NAMES[fmt]
    if fmt == "html":
        return _mathml_to_html_fragment(mathml_converter(clean)), FORMAT_DISPLAY_NAMES[fmt]
    if fmt == "mathml":
        return mathml_converter(clean), FORMAT_DISPLAY_NAMES[fmt]
    if fmt == "mathml_mml":
        return _mathml_with_prefix(mathml_converter(clean), "mml"), FORMAT_DISPLAY_NAMES[fmt]
    if fmt == "mathml_m":
        return _mathml_with_prefix(mathml_converter(clean), "m"), FORMAT_DISPLAY_NAMES[fmt]
    if fmt == "mathml_attr":
        return _mathml_with_prefix(mathml_converter(clean), "attr"), FORMAT_DISPLAY_NAMES[fmt]
    if fmt == "omml":
        return omml_converter(clean), FORMAT_DISPLAY_NAMES[fmt]
    if fmt == "svgcode":
        return svg_converter(clean), FORMAT_DISPLAY_NAMES[fmt]
    return "", ""
