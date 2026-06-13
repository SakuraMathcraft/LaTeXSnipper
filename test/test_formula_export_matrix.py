from __future__ import annotations

import json
from pathlib import Path
import shutil
import subprocess
import xml.etree.ElementTree as ET

import pytest

from exporting import formula_converters
from exporting.formula_converters import _find_mml2omml_xsl
from exporting.formula_export import build_formula_export, get_all_export_format_specs
from exporting.pandoc_exporter import check_pandoc_available


SAMPLE_LATEX = (
    r"\frac{d}{dt}\frac{\partial L}{\partial \dot q_i}"
    r"-\frac{\partial L}{\partial q_i}=0"
)


@pytest.fixture(scope="module")
def local_mathjax_result() -> dict[str, str]:
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node.js is unavailable for bundled MathJax verification")

    mathjax = (
        Path(__file__).parents[1]
        / "src"
        / "assets"
        / "MathJax-3.2.2"
        / "es5"
        / "node-main.js"
    )
    script = r"""
const mathjaxPath = process.argv[1];
const source = process.argv[2];
const loader = require(mathjaxPath);
loader.init({
  loader: {
    load: [
      'input/tex',
      'output/svg',
      '[tex]/bbox',
      '[tex]/boldsymbol',
      '[tex]/color',
      '[tex]/enclose',
      '[tex]/mhchem'
    ]
  },
  tex: {
    packages: {
      '[+]': ['bbox', 'boldsymbol', 'color', 'enclose', 'mhchem']
    }
  },
  svg: {fontCache: 'none'}
}).then(MathJax => {
  const mathml = MathJax.tex2mml(source, {display: true});
  const container = MathJax.tex2svg(source, {display: true});
  const adaptor = MathJax.startup.adaptor;
  const svg = adaptor.outerHTML(adaptor.firstChild(container));
  process.stdout.write(JSON.stringify({mathml, svg}));
}).catch(error => {
  console.error(error);
  process.exit(1);
});
"""
    completed = subprocess.run(
        [node, "-e", script, str(mathjax), SAMPLE_LATEX],
        check=True,
        capture_output=True,
        text=True,
        timeout=30,
    )
    return json.loads(completed.stdout)


def test_export_registry_contains_exactly_30_formats() -> None:
    if not check_pandoc_available(force=True):
        pytest.skip("Pandoc backend is not installed")

    keys = [
        spec.key
        for spec in get_all_export_format_specs()
        if spec.key and not spec.key.startswith("_")
    ]
    assert len(keys) == 30
    assert len(keys) == len(set(keys))


def test_all_native_exports_use_real_bundled_mathjax(
    monkeypatch: pytest.MonkeyPatch,
    local_mathjax_result: dict[str, str],
) -> None:
    monkeypatch.setattr(
        formula_converters,
        "convert_latex_with_mathjax",
        lambda _latex: dict(local_mathjax_result),
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
