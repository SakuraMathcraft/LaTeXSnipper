"""Formula conversion helpers used by export actions."""

from __future__ import annotations

import importlib.util
import os

from exporting.formula_format_helpers import (
    latex_to_svg,
    mathml_standardize,
    normalize_latex_for_export,
)


def _pypandoc_available() -> bool:
    """Check whether pypandoc can be imported."""
    try:
        return importlib.util.find_spec("pypandoc") is not None
    except Exception:
        return False


def convert_typst_to_latex(typst: str) -> str:
    """Convert Typst math formula to LaTeX via pypandoc.

    Returns the original Typst string if pypandoc is unavailable or
    the conversion fails.
    """
    if not typst or not typst.strip():
        return ""
    if not _pypandoc_available():
        return typst
    try:
        import pypandoc
        result = str(pypandoc.convert_text(typst.strip(), "latex", format="typst")).strip()
        if result:
            return result
    except Exception:
        pass
    return typst


def get_current_render_mode() -> str:
    """Return the current formula render mode ('typst', 'latex_pdflatex', etc.).

    Returns 'auto' if settings are unavailable.
    """
    try:
        from backend.latex_renderer import _latex_settings
        if _latex_settings:
            return _latex_settings.get_render_mode()
    except Exception:
        pass
    return "auto"


def latex_to_svg_code(latex: str) -> str:
    return latex_to_svg(latex)


def latex_to_mathml(latex: str) -> str:
    latex = normalize_latex_for_export(latex)
    import latex2mathml.converter

    mathml = latex2mathml.converter.convert(latex)
    return mathml_standardize(mathml)


def latex_to_omml(latex: str) -> str:
    """Convert LaTeX to Office Math Markup Language, falling back to MathML."""
    try:
        latex = normalize_latex_for_export(latex)
        import latex2mathml.converter

        mathml = latex2mathml.converter.convert(latex)

        try:
            from lxml import etree

            xsl_paths = [
                os.path.expandvars(r"%ProgramFiles%\Microsoft Office\root\Office16\MML2OMML.XSL"),
                os.path.expandvars(r"%ProgramFiles(x86)%\Microsoft Office\root\Office16\MML2OMML.XSL"),
                os.path.expandvars(r"%ProgramFiles%\Microsoft Office\Office16\MML2OMML.XSL"),
                os.path.expandvars(r"%ProgramFiles%\Microsoft Office\Office19\MML2OMML.XSL"),
            ]

            xsl_path = next((p for p in xsl_paths if os.path.exists(p)), None)
            if xsl_path:
                xsl_doc = etree.parse(xsl_path)
                transform = etree.XSLT(xsl_doc)
                mathml_doc = etree.fromstring(mathml.encode("utf-8"))
                omml_doc = transform(mathml_doc)
                result = etree.tostring(omml_doc, encoding="unicode")
                return result if result else mathml
        except Exception:
            return mathml

        return mathml
    except ImportError:
        escaped = latex.replace("\\", "\\\\").replace("{", "\\{").replace("}", "\\}")
        return f"{{ EQ \\\\o\\\\al(\\\\lc\\\\(({escaped})\\\\rc\\\\))"
