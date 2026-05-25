"""Formula conversion helpers used by export actions."""

from __future__ import annotations

import os
from pathlib import Path

from exporting.formula_format_helpers import (
    latex_to_svg,
    mathml_standardize,
    normalize_latex_for_export,
)


def latex_to_svg_code(latex: str) -> str:
    return latex_to_svg(latex)


def latex_to_mathml(latex: str) -> str:
    latex = normalize_latex_for_export(latex)
    import latex2mathml.converter

    mathml = latex2mathml.converter.convert(latex)
    return mathml_standardize(mathml)


def latex_to_omml(latex: str) -> str:
    """Convert LaTeX to Office Math Markup Language.

    This function must return real OMML. MathML fallback belongs to the MathML
    export formats, not to the OMML export path.
    """
    latex = normalize_latex_for_export(latex)
    import latex2mathml.converter
    from lxml import etree

    mathml = mathml_standardize(latex2mathml.converter.convert(latex))
    xsl_path = _find_mml2omml_xsl()
    if xsl_path is None:
        raise RuntimeError("Microsoft MML2OMML.XSL was not found; cannot export real OMML")

    xsl_doc = etree.parse(str(xsl_path))
    transform = etree.XSLT(xsl_doc)
    mathml_doc = etree.fromstring(mathml.encode("utf-8"))
    omml_doc = transform(mathml_doc)
    result = etree.tostring(omml_doc, encoding="unicode")
    if not _looks_like_omml(result):
        raise RuntimeError("MML2OMML conversion did not produce OMML")
    return result


def _find_mml2omml_xsl() -> Path | None:
    candidates = [
        os.path.expandvars(r"%ProgramFiles%\Microsoft Office\root\Office16\MML2OMML.XSL"),
        os.path.expandvars(r"%ProgramFiles(x86)%\Microsoft Office\root\Office16\MML2OMML.XSL"),
        os.path.expandvars(r"%ProgramFiles%\Microsoft Office\Office16\MML2OMML.XSL"),
        os.path.expandvars(r"%ProgramFiles%\Microsoft Office\Office19\MML2OMML.XSL"),
    ]
    for candidate in candidates:
        path = Path(candidate)
        if path.is_file():
            return path
    return None


def _looks_like_omml(value: str) -> bool:
    text = str(value or "")
    return "<m:oMath" in text or "<m:oMathPara" in text
