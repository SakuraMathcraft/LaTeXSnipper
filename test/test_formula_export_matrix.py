from __future__ import annotations

import json
from pathlib import Path
import shutil
import subprocess
import xml.etree.ElementTree as ET

import pytest

from exporting import formula_converters
from exporting.formula_converters import _find_mml2omml_xsl
from exporting.formula_export import build_formula_export, export_format_label, get_all_export_format_specs, is_export_format_available
from exporting.formula_format_helpers import normalize_latex_for_export
from exporting.pandoc_exporter import check_pandoc_available


SAMPLE_LATEX = (
    r"\frac{d}{dt}\frac{\partial L}{\partial \dot q_i}"
    r"-\frac{\partial L}{\partial q_i}=0"
)


def run_mathjax(inputs: list[dict], *, font: str = "mathjax-tex") -> dict:
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node.js is unavailable for bundled MathJax verification")
    completed = subprocess.run(
        [node, str(Path(__file__).parents[1] / "tools/mathjax/probe.cjs"), json.dumps({"font": font})],
        input=json.dumps(inputs), check=True, capture_output=True, text=True, encoding="utf-8", timeout=30,
    )
    assert not completed.stderr, completed.stderr
    return json.loads(completed.stdout)


@pytest.fixture(scope="module")
def local_mathjax_result() -> dict[str, str]:
    return run_mathjax([{"latex": SAMPLE_LATEX}])["results"][0]


def test_export_registry_contains_exactly_formats() -> None:
    if not check_pandoc_available(force=True):
        pytest.skip("Pandoc backend is not installed")

    keys = [
        spec.key
        for spec in get_all_export_format_specs()
        if spec.key and not spec.key.startswith("_")
    ]
    assert len(keys) == 20
    assert len(keys) == len(set(keys))


def test_export_format_lookup_supports_quick_export_preference() -> None:
    assert is_export_format_available("latex")
    assert export_format_label("latex") == "LaTeX (行内 $...$)"
    assert not is_export_format_available("")
    assert not is_export_format_available("_pandoc_header")


def test_export_normalization_preserves_latex_source() -> None:
    source = r"\text{a    b}:=\alpha^{2}+x_{i}\frac{1}{2}"
    converters = {
        "mathml_converter": lambda value: value,
        "omml_converter": lambda value: value,
        "svg_converter": lambda value: value,
    }

    assert normalize_latex_for_export(source) == source
    assert build_formula_export("latex", source, **converters)[0] == f"${source}$"
    assert build_formula_export("latex_display", source, **converters)[0] == f"\\[\n{source}\n\\]"
    assert build_formula_export("latex_equation", source, **converters)[0] == (
        f"\\begin{{equation}}\n{source}\n\\end{{equation}}"
    )
    assert build_formula_export("markdown_inline", source, **converters)[0] == f"${source}$"
    assert build_formula_export("markdown_block", source, **converters)[0] == f"$$\n{source}\n$$"


def test_export_normalization_only_removes_unambiguous_outer_delimiter() -> None:
    source = r"\text{cost \$5} + x^{2}"

    assert normalize_latex_for_export(f"  $${source}$$  ") == source
    assert normalize_latex_for_export(f"${source}$") == source
    assert normalize_latex_for_export("  $  x^{2}  $  ") == "  x^{2}  "
    assert normalize_latex_for_export("$a$ and $b$") == "$a$ and $b$"


@pytest.mark.parametrize("font", ["mathjax-tex", "mathjax-stix2"])
def test_bundled_mathjax_renders_shared_packages_and_dynamic_fonts(font: str) -> None:
    samples = [
        r"\mathcal{e^{i\pi}+1=0}", r"\mathscr{ABC}", r"\mathfrak{ABC}", r"\mathbb{ABC}",
        r"\qty(\frac{a}{b})+\dv{f}{x}+\vb{E}", r"\braket{\psi|\phi}+\ketbra{0}{1}",
        r"\cancel{x}+\bcancel{y}+\xcancel{z}",
        r"\begin{cases}x^2,&x>0\\0,&x\le0\end{cases}",
        r"A\xrightarrow[\beta]{\alpha}B+\ce{CO2 + C -> 2 CO}",
        r"\begin{align}&\text{设 }A,B\text{ 为事件}\\&P(A\mid B)=\frac{P(A\cap B)}{P(B)}\end{align}",
        r"\mathrm{\delta}", '<math><mfrac><mi>a</mi><mi>b</mi></mfrac></math>',
    ]
    data = run_mathjax([{"latex": sample} for sample in samples], font=font)
    for result in data["results"]:
        assert result["version"] == "4.1.3"
        assert "data-mjx-error" not in result["svg"] and "merror" not in result["mathml"]
        ET.fromstring(result["svg"])
        ET.fromstring(result["mathml"])
    assert any("mhchem-font-extension" in file for file in data["loaded"])
    if font == "mathjax-stix2":
        assert any("mathjax-stix2-font/svg/" in file for file in data["loaded"])


def test_mathml_only_does_not_run_svg_and_office_normalization_is_explicit() -> None:
    results = run_mathjax([
        {"latex": "x", "outputs": ["mathml"]},
        {"latex": r"\colorbox{red}{$x$}", "outputs": ["svg"], "officeInput": True},
    ])["results"]
    assert "svg" not in results[0]
    assert "mathml" not in results[1]
    assert "data-mjx-error" not in results[1]["svg"]


def test_all_native_exports_use_real_bundled_mathjax(
    monkeypatch: pytest.MonkeyPatch,
    local_mathjax_result: dict[str, str],
) -> None:
    monkeypatch.setattr(
        formula_converters,
        "convert_latex_with_mathjax",
        lambda _latex, **_kwargs: dict(local_mathjax_result),
    )

    converters = {
        "mathml_converter": formula_converters.latex_to_mathml,
        "omml_converter": formula_converters.latex_to_omml,
        "svg_converter": formula_converters.latex_to_svg_code,
    }
    text_results = {
        key: build_formula_export(key, SAMPLE_LATEX, **converters)[0]
        for key in (
            "latex",
            "latex_display",
            "latex_equation",
            "markdown_inline",
            "markdown_block",
            "mathml",
            "mathml_mml",
            "mathml_m",
            "mathml_attr",
            "html",
            "svgcode",
        )
    }

    assert text_results["latex"].startswith("$")
    assert text_results["latex_display"].startswith("\\[")
    assert text_results["latex_equation"].startswith("\\begin{equation}")
    assert text_results["markdown_inline"] == text_results["latex"]
    assert text_results["markdown_block"].startswith("$$\n")

    mathml_root = ET.fromstring(text_results["mathml"])
    assert mathml_root.tag.endswith("}math")
    assert any(node.tag.endswith("}mfrac") for node in mathml_root.iter())
    assert any(node.tag.endswith("}msub") for node in mathml_root.iter())

    for key in ("mathml_mml", "mathml_m", "mathml_attr"):
        root = ET.fromstring(text_results[key])
        assert root.tag.endswith("}math"), key

    assert '<span class="latexsnipper-math"' in text_results["html"]
    assert "<math" in text_results["html"]

    svg_root = ET.fromstring(text_results["svgcode"])
    assert svg_root.tag.endswith("}svg")
    assert svg_root.get("viewBox")
    assert any(node.tag.endswith("}path") for node in svg_root.iter())

    if _find_mml2omml_xsl() is None:
        pytest.skip("Microsoft MML2OMML.XSL is unavailable")
    omml, _ = build_formula_export("omml", SAMPLE_LATEX, **converters)
    omml_root = ET.fromstring(omml)
    assert "officeDocument/2006/math" in omml_root.tag
    assert any(node.tag.endswith("}f") for node in omml_root.iter())
