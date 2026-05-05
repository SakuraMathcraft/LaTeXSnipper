"""Formula conversion helpers used by export actions."""

from __future__ import annotations

import os

from preview.math_preview import (
    mathml_standardize,
    normalize_latex_for_export,
    latex_to_svg,
)


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
