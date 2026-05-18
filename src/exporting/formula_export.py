"""Formula export format registry and conversion dispatcher."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Callable

from exporting.formula_format_helpers import (
    latex_display,
    latex_equation,
    latex_inline,
    mathml_to_html_fragment,
    mathml_with_prefix,
    normalize_latex_for_export,
)

# Lazy import for Pandoc availability check
def _pandoc_available() -> bool:
    try:
        from exporting.pandoc_exporter import is_available
        return is_available()
    except Exception:
        return False


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

# Pandoc formats are added dynamically when Pandoc is available
def _get_pandoc_format_specs() -> tuple[ExportFormatSpec, ...]:
    """Return Pandoc format specs if Pandoc is available."""
    if not _pandoc_available():
        return ()
    from exporting.pandoc_exporter import PANDOC_FORMATS
    specs = [ExportFormatSpec("", separator_before=True)]
    specs.append(ExportFormatSpec("_pandoc_header", "── Pandoc 导出 ──"))
    for fmt in PANDOC_FORMATS:
        specs.append(ExportFormatSpec(fmt.key, fmt.label))
    return tuple(specs)

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


def get_all_export_format_specs() -> tuple[ExportFormatSpec, ...]:
    """Return all format specs, including Pandoc formats when available."""
    return EXPORT_FORMAT_SPECS + _get_pandoc_format_specs()


def build_formula_export(
    format_type: str,
    latex: str,
    *,
    mathml_converter: Callable[[str], str],
    omml_converter: Callable[[str], str],
    svg_converter: Callable[[str], str],
) -> tuple[str, str]:
    """Return (export_text, display_name) for a formula export format."""
    clean = normalize_latex_for_export(latex)
    fmt = str(format_type or "").strip()

    if fmt == "latex":
        return latex_inline(clean), FORMAT_DISPLAY_NAMES[fmt]
    if fmt == "latex_display":
        return latex_display(clean), FORMAT_DISPLAY_NAMES[fmt]
    if fmt == "latex_equation":
        return latex_equation(clean), FORMAT_DISPLAY_NAMES[fmt]
    if fmt == "markdown_inline":
        return latex_inline(clean), FORMAT_DISPLAY_NAMES[fmt]
    if fmt == "markdown_block":
        return f"$$\n{clean}\n$$", FORMAT_DISPLAY_NAMES[fmt]
    if fmt == "html":
        return mathml_to_html_fragment(mathml_converter(clean)), FORMAT_DISPLAY_NAMES[fmt]
    if fmt == "mathml":
        return mathml_converter(clean), FORMAT_DISPLAY_NAMES[fmt]
    if fmt == "mathml_mml":
        return mathml_with_prefix(mathml_converter(clean), "mml"), FORMAT_DISPLAY_NAMES[fmt]
    if fmt == "mathml_m":
        return mathml_with_prefix(mathml_converter(clean), "m"), FORMAT_DISPLAY_NAMES[fmt]
    if fmt == "mathml_attr":
        return mathml_with_prefix(mathml_converter(clean), "attr"), FORMAT_DISPLAY_NAMES[fmt]
    if fmt == "omml":
        return omml_converter(clean), FORMAT_DISPLAY_NAMES[fmt]
    if fmt == "svgcode":
        return svg_converter(clean), FORMAT_DISPLAY_NAMES[fmt]

    # Pandoc formats
    if fmt.startswith("pandoc_"):
        return _build_pandoc_export(fmt, clean)

    return "", ""


def _build_pandoc_export(format_key: str, latex: str) -> tuple[str, str]:
    """Build export result using Pandoc backend.

    Returns (export_text, display_name). For binary formats, returns a
    placeholder string indicating binary data is available.
    """
    from exporting.pandoc_exporter import (
        PANDOC_FORMAT_MAP,
        PandocNotAvailable,
        convert_latex_to,
        get_format_label,
    )

    fmt = PANDOC_FORMAT_MAP.get(format_key)
    if fmt is None:
        return "", ""

    label = get_format_label(format_key)

    # When targeting Typst and the input is already Typst syntax (no LaTeX
    # backslash commands like \\alpha, \\frac, \\sum), return it directly
    # without pandoc.  Passing Typst-as-LaTeX makes pandoc treat keywords
    # like "sum" / "integral" / "infinity" as italic-letter products and
    # insert spaces between every character.
    if format_key == "pandoc_typst":
        clean_body = (latex or "").strip()
        if not _looks_like_latex_math(clean_body):
            return clean_body, label

    try:
        result = convert_latex_to(format_key, latex, as_document=True)
    except PandocNotAvailable as exc:
        return f"[Pandoc 不可用] {exc}", label
    except Exception as exc:
        return f"[Pandoc 转换失败] {exc}", label

    if isinstance(result, bytes):
        # Binary format: return a marker; caller should handle file saving
        return f"[BINARY:{format_key}]", label

    # Clean up pandoc artifacts for Typst output: pandoc converts \\infty
    # to "oo", escapes parentheses and slashes, and wraps in $ delimiters.
    if format_key == "pandoc_typst" and isinstance(result, str):
        result = _clean_pandoc_typst_output(result)

    return result, label


def _looks_like_latex_math(text: str) -> bool:
    """Return True if *text* contains LaTeX backslash commands."""
    return bool(text and re.search(r'\\[a-zA-Z]', text))


def _clean_pandoc_typst_output(typst: str) -> str:
    r"""Clean up pandoc conversion artifacts in Typst math output.

    Pandoc may produce artifacts such as:
    - ``\\infty`` converted to ``oo`` (should be ``infinity``)
    - Escaped parentheses ``\\(`` ``\\)``
    - Escaped slashes ``\\/``
    - ``{= X)`` malformed patterns from subscript conversion
    - Orphaned trailing ``}`` braces
    - ``$`` delimiters

    >>> _clean_pandoc_typst_output('$ sum_(n {= 1)^oo 1 / n^2 $')
    'sum_(n = 1)^infinity 1 / n^2'
    """
    text = (typst or "").strip()
    # Strip $ math delimiters pandoc may add
    text = text.replace('$', '')
    # Fix pandoc artifact: {= X)  ->  = X)
    text = re.sub(r'\{=\s*([^}{)]*)\)', r'= \1)', text)
    # Fix pandoc converting \infty to "oo" (should be "infinity" in Typst).
    text = re.sub(r'\boo\b', 'infinity', text)
    # Fix pandoc escaping \, (, ), / in Typst output
    text = text.replace(r'\(', '(')
    text = text.replace(r'\)', ')')
    text = text.replace(r'\/', '/')
    # Strip orphaned trailing } left over from pandoc conversion
    while text.endswith('}') and text.count('{') < text.count('}'):
        text = text[:-1]
    return text.strip()
