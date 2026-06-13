# coding: utf-8

from __future__ import annotations

import pytest

import exporting.formula_converters as formula_converters
from exporting.formula_converters import (
    _find_mml2omml_xsl,
    latex_to_mathml,
    latex_to_omml,
    latex_to_svg_code,
)


@pytest.fixture(autouse=True)
def stub_mathjax_conversion(monkeypatch):
    def convert(latex: str) -> dict[str, str]:
        if "horizontalstrike" in latex:
            mathml = (
                '<math xmlns="http://www.w3.org/1998/Math/MathML">'
                '<menclose notation="horizontalstrike"><mrow><mi>x</mi><mo>+</mo><mi>y</mi></mrow></menclose>'
                "</math>"
            )
        elif "aligned" in latex:
            mathml = (
                '<math xmlns="http://www.w3.org/1998/Math/MathML"><mtable>'
                "<mtr><mtd><msub><mi>x</mi><mi>n</mi></msub></mtd><mtd><mo>=</mo></mtd>"
                "<mtd><munderover><mo>∑</mo><mrow><mi>k</mi><mo>=</mo><mn>1</mn></mrow>"
                "<mi>n</mi></munderover></mtd></mtr></mtable></math>"
            )
        elif r"\int" in latex:
            mathml = (
                '<math xmlns="http://www.w3.org/1998/Math/MathML"><mrow>'
                "<msubsup><mo>∫</mo><mn>0</mn><mn>1</mn></msubsup>"
                "<msup><mi>x</mi><mn>2</mn></msup><mi>d</mi><mi>x</mi></mrow></math>"
            )
        else:
            mathml = (
                '<math xmlns="http://www.w3.org/1998/Math/MathML">'
                "<msup><mi>x</mi><mn>2</mn></msup></math>"
            )
        return {"mathml": mathml, "svg": '<svg xmlns="http://www.w3.org/2000/svg"><path d="M0 0"/></svg>'}

    monkeypatch.setattr(formula_converters, "convert_latex_with_mathjax", convert)


def test_mathjax_exports_mathlive_horizontal_strike() -> None:
    mathml = latex_to_mathml(r"\enclose{horizontalstrike}{x+y}")
    assert '<menclose notation="horizontalstrike">' in mathml


def test_mathjax_exports_standalone_svg() -> None:
    svg = latex_to_svg_code(r"x^2")

    assert svg.startswith("<svg")
    assert "<path" in svg


def test_latex_to_omml_returns_real_omml_for_simple_formula() -> None:
    if _find_mml2omml_xsl() is None:
        pytest.skip("Microsoft MML2OMML.XSL is not available on this runner")

    result = latex_to_omml("x^2")

    assert "<m:oMath" in result
    assert "<math" not in result


def test_latex_to_omml_handles_aligned_formula_without_mathml_fallback() -> None:
    if _find_mml2omml_xsl() is None:
        pytest.skip("Microsoft MML2OMML.XSL is not available on this runner")

    latex = r"""
\begin{aligned}
x _ { n } &= \sum _ { k = 1 } ^ { n - p - 1 } \frac { 1 } { n + k } \\
&= \left( \sum _ { k = 1 } ^ { n - p - 1 } \frac { 1 } { n + k } \right)
\end{aligned}
"""

    result = latex_to_omml(latex)

    assert "<m:oMath" in result
    assert "<math" not in result
    assert "<mi>&</mi>" not in result


def test_latex_to_omml_repairs_empty_integral_body() -> None:
    if _find_mml2omml_xsl() is None:
        pytest.skip("Microsoft MML2OMML.XSL is not available on this runner")

    result = latex_to_omml(r"\int_0^1x^2\,dx")

    assert "<m:oMath" in result
    assert "<m:e/>" not in result
    assert "<m:e></m:e>" not in result
