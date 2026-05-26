"""Formula conversion helpers used by export actions."""

from __future__ import annotations

import importlib.util
import os
from pathlib import Path
import copy

from backend.typst_utils import clean_typst_to_latex_output, _strip_typst_grouping_for_reverse
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

    Automatically strips ``$$..$$`` user-facing delimiters before
    conversion and wraps the body in Typst math delimiters so that
    pypandoc recognises it as a math expression.
    Returns the original Typst string if pypandoc is unavailable or
    the conversion fails.
    """
    text = typst or ""
    if not text.strip():
        return ""
    body = text.strip()
    import re
    body = re.sub(r'^\$\$\s*', '', body)
    body = re.sub(r'\s*\$\$\s*$', '', body)
    # Strip Typst math delimiters ($...$) from the body so pypandoc only
    # sees the raw math content.  $ is never valid inside a Typst math
    # expression, so stripping all occurrences here is safe.
    body = body.replace('$', '')
    body = body.strip()
    if not body:
        return text
    if not _pypandoc_available():
        return text if text != body else body
    try:
        import pypandoc
        # Strip {} grouping added by forward conversion, which pandoc's
        # Typst reader cannot handle inside function arguments like
        # sqrt(sum_(...)^(...) {body}).
        body = _strip_typst_grouping_for_reverse(body)
        wrapped = "$ " + body + " $"
        result = str(pypandoc.convert_text(wrapped, "latex", format="typst")).strip()
        if result:
            result = clean_typst_to_latex_output(result)
            if result:
                return result
    except Exception:
        pass
    return body


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
    return _repair_empty_nary_operands(result)


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


def _repair_empty_nary_operands(omml: str) -> str:
    from lxml import etree

    ns = {"m": "http://schemas.openxmlformats.org/officeDocument/2006/math"}
    root = etree.fromstring(omml.encode("utf-8"))
    for nary in root.xpath(".//m:nary[m:e[not(node())]]", namespaces=ns):
        body = nary.find("m:e", namespaces=ns)
        if body is None:
            continue
        parent = nary.getparent()
        if parent is None:
            continue
        siblings = list(parent)
        try:
            nary_index = siblings.index(nary)
        except ValueError:
            continue
        for candidate in siblings[nary_index + 1 :]:
            if candidate.tag.endswith("}r") and "".join(candidate.itertext()).strip() == "":
                continue
            body.append(copy.deepcopy(candidate))
            parent.remove(candidate)
            break
    return etree.tostring(root, encoding="unicode")
