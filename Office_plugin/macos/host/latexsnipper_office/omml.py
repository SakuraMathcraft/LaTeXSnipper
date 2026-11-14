"""MathML to Word OMML with LaTeXSnipper typography.

Ports ``OmmlTypographyMapper`` from the Windows plugin: Word owns equation
layout, while the formula's symbol, number and CJK fonts, size and color are
applied as run properties that local source styles still override.
"""

from __future__ import annotations

import copy
import re
from functools import lru_cache
from pathlib import Path

from latexsnipper_office.typography import Typography

MATH = "http://schemas.openxmlformats.org/officeDocument/2006/math"
WORD = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
SYMBOL_FAMILIES = {"mathjax-tex": "Cambria Math", "mathjax-stix2": "STIX Two Math"}
_NUMBER = re.compile(r"\A\d+(?:[.,]\d+)*\Z")


# Word for Mac ships Microsoft's converter inside its app bundle.
WORD_STYLESHEET = "Microsoft Word.app/Contents/Resources/mathml2omml.xsl"


class StylesheetUnavailable(RuntimeError):
    pass


def application_directories() -> tuple[Path, ...]:
    return (Path("/Applications"), Path.home() / "Applications")


def find_stylesheet() -> Path | None:
    for directory in application_directories():
        stylesheet = directory / WORD_STYLESHEET
        if stylesheet.is_file():
            return stylesheet
    return None


@lru_cache(maxsize=1)
def _transform(path: str):
    from lxml import etree

    parser = etree.XMLParser(resolve_entities=False, no_network=True, load_dtd=False)
    return etree.XSLT(etree.parse(path, parser))


def convert(mathml: str, typography: Typography) -> str:
    return apply_typography(mathml_to_omml(mathml), typography)


def mathml_to_omml(mathml: str) -> str:
    """Convert MathML with the stylesheet of the Word installation being served."""
    from lxml import etree

    stylesheet = find_stylesheet()
    if stylesheet is None:
        raise StylesheetUnavailable(str(WORD_STYLESHEET))
    parser = etree.XMLParser(resolve_entities=False, no_network=True, load_dtd=False)
    document = etree.fromstring(mathml.encode("utf-8"), parser)
    result = etree.tostring(_transform(str(stylesheet))(document), encoding="unicode")
    if "<m:oMath" not in result:
        raise ValueError("MathML conversion did not produce OMML")
    return _repair_empty_nary_operands(result)


def _repair_empty_nary_operands(omml: str) -> str:
    """Move the operand that Microsoft's stylesheet leaves after an empty n-ary body into it."""
    from lxml import etree

    ns = {"m": MATH}
    root = etree.fromstring(omml.encode("utf-8"))
    for nary in root.xpath(".//m:nary[m:e[not(node())]]", namespaces=ns):
        body = nary.find("m:e", namespaces=ns)
        parent = nary.getparent()
        if body is None or parent is None:
            continue
        siblings = list(parent)
        for candidate in siblings[siblings.index(nary) + 1 :]:
            if (
                candidate.tag.endswith("}r")
                and "".join(candidate.itertext()).strip() == ""
            ):
                continue
            body.append(copy.deepcopy(candidate))
            parent.remove(candidate)
            break
    return etree.tostring(root, encoding="unicode")


def apply_typography(omml: str, typography: Typography) -> str:
    from lxml import etree

    parser = etree.XMLParser(resolve_entities=False, no_network=True, load_dtd=False)
    root = etree.fromstring(omml.encode("utf-8"), parser)
    if root.tag not in {f"{{{MATH}}}oMath", f"{{{MATH}}}oMathPara"}:
        raise ValueError("需要 OMML 公式根节点。")
    symbol = SYMBOL_FAMILIES.get(typography.symbol_font_id)
    if symbol is None:
        raise ValueError("不支持的数学字体方案。")
    size = str(int(typography.font_size_points * 2 + 0.5))
    color = typography.color[1:]
    for run in root.iter(f"{{{MATH}}}r"):
        text = "".join(node.text or "" for node in run.findall(f"{{{MATH}}}t"))
        normal = run.find(f"{{{MATH}}}rPr/{{{MATH}}}nor")
        value = None if normal is None else normal.get(f"{{{MATH}}}val")
        is_text = normal is not None and value not in {"0", "false"}
        is_number = not is_text and bool(_NUMBER.match(text))
        family = (
            "Times New Roman"
            if is_text
            else typography.number_font_family
            if is_number and typography.number_font_family
            else symbol
        )
        properties = run.find(f"{{{WORD}}}rPr")
        if properties is None:
            properties = etree.Element(f"{{{WORD}}}rPr", nsmap={"w": WORD})
            math_properties = run.find(f"{{{MATH}}}rPr")
            if math_properties is None:
                run.insert(0, properties)
            else:
                math_properties.addnext(properties)
        fonts = properties.find(f"{{{WORD}}}rFonts")
        if fonts is None:
            fonts = etree.Element(f"{{{WORD}}}rFonts", nsmap={"w": WORD})
            properties.insert(0, fonts)
        fonts.set(f"{{{WORD}}}ascii", family)
        fonts.set(f"{{{WORD}}}hAnsi", family)
        fonts.set(f"{{{WORD}}}eastAsia", typography.cjk_font_family)
        for theme in ("asciiTheme", "hAnsiTheme", "eastAsiaTheme"):
            fonts.attrib.pop(f"{{{WORD}}}{theme}", None)
        for name, setting in (("color", color), ("sz", size), ("szCs", size)):
            if properties.find(f"{{{WORD}}}{name}") is None:
                element = etree.SubElement(properties, f"{{{WORD}}}{name}")
                element.set(f"{{{WORD}}}val", setting)
    return etree.tostring(root, encoding="unicode")
