"""Formula conversion helpers used by export actions."""

from __future__ import annotations

import copy
import sys
from functools import lru_cache
from pathlib import Path

from exporting.formula_format_helpers import (
    mathml_standardize,
    normalize_latex_for_export,
)
from exporting.mathjax_converter import convert_latex_with_mathjax


def latex_to_svg_code(latex: str) -> str:
    latex = normalize_latex_for_export(latex)
    return convert_latex_with_mathjax(latex, outputs=("svg",))["svg"]


def latex_to_mathml(latex: str) -> str:
    latex = normalize_latex_for_export(latex)
    mathml = convert_latex_with_mathjax(latex, outputs=("mathml",))["mathml"]
    return mathml_standardize(mathml)


def latex_to_omml(latex: str) -> str:
    """Convert LaTeX to Office Math Markup Language.

    This function must return real OMML. MathML fallback belongs to the MathML
    export formats, not to the OMML export path.
    """
    latex = normalize_latex_for_export(latex)
    import lxml.etree as etree

    mathml = mathml_standardize(
        convert_latex_with_mathjax(latex, outputs=("mathml",))["mathml"]
    )
    mathml_doc = etree.fromstring(mathml.encode("utf-8"))
    omml_doc = _cached_mml2omml_transform()(mathml_doc)
    result = etree.tostring(omml_doc, encoding="unicode")
    if not _looks_like_omml(result):
        raise RuntimeError("MML2OMML conversion did not produce OMML")
    return _repair_empty_nary_operands(result)


def _find_mml2omml_xsl() -> Path | None:
    if sys.platform != "win32":
        return None

    import winreg

    key_path = r"Software\Microsoft\Windows\CurrentVersion\App Paths\WINWORD.EXE"
    for hive in (winreg.HKEY_CURRENT_USER, winreg.HKEY_LOCAL_MACHINE):
        for view in (winreg.KEY_WOW64_64KEY, winreg.KEY_WOW64_32KEY):
            try:
                with winreg.OpenKey(hive, key_path, 0, winreg.KEY_READ | view) as key:
                    executable, value_type = winreg.QueryValueEx(key, "")
                if value_type == winreg.REG_EXPAND_SZ:
                    executable = winreg.ExpandEnvironmentStrings(executable)
                elif value_type != winreg.REG_SZ:
                    continue
            except OSError:
                continue

            word_path = Path(executable.strip().strip('"'))
            if not word_path.is_absolute() or not word_path.is_file():
                continue
            stylesheet = word_path.with_name("MML2OMML.XSL")
            if stylesheet.is_file():
                return stylesheet
    return None


@lru_cache(maxsize=1)
def _cached_mml2omml_transform():
    import lxml.etree as etree

    xsl_path = _find_mml2omml_xsl()
    if xsl_path is None:
        raise RuntimeError(
            "Microsoft MML2OMML.XSL was not found; cannot export real OMML"
        )
    xsl_doc = etree.parse(str(xsl_path))
    return etree.XSLT(xsl_doc)


def _looks_like_omml(value: str) -> bool:
    text = str(value or "")
    return "<m:oMath" in text or "<m:oMathPara" in text


def _repair_empty_nary_operands(omml: str) -> str:
    import lxml.etree as etree

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
            if (
                candidate.tag.endswith("}r")
                and "".join(candidate.itertext()).strip() == ""
            ):
                continue
            body.append(copy.deepcopy(candidate))
            parent.remove(candidate)
            break
    return etree.tostring(root, encoding="unicode")
