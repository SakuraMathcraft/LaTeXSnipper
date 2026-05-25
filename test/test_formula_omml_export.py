# coding: utf-8

from __future__ import annotations

import pytest

from exporting.formula_converters import _find_mml2omml_xsl, latex_to_omml


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
