import json
import subprocess
import sys
from pathlib import Path

from exporting.pandoc_exporter import _ensure_mathjax_script
from rendering.mathjax_runtime import ASSET_ROOT, cdn_root, loader_script


def test_pandoc_replaces_pinned_loader_once_and_preserves_source():
    source = r"\(\mathrm{\delta}+\text{中文}\)"
    html = (
        '<html><head><script defer src="'
        + cdn_root()
        + '/startup.js"></script></head><body><span class="math inline">'
        + source
        + "</span></body></html>"
    )
    result = _ensure_mathjax_script(html)
    assert source in result
    assert result.count("LaTeXSnipperMathJax.load(") == 1
    assert "<script defer" not in result
    assert cdn_root() in result
    assert "https://cdn.jsdelivr.net/npm/@mathjax" in result
    assert ASSET_ROOT.resolve().as_uri() not in result
    assert "officeInput" not in result.split("LaTeXSnipperMathJax.load(")[-1]


def test_plain_html_needs_no_mathjax():
    html = "<html><body>Plain text</body></html>"
    assert _ensure_mathjax_script(html) == html


def test_resource_profiles_are_reproducible_and_office_is_self_contained():
    root = Path(__file__).resolve().parents[1]
    subprocess.run(
        [
            sys.executable,
            "-X",
            "utf8",
            str(root / "tools/mathjax/prepare.py"),
            "--verify",
        ],
        check=True,
    )
    manifest = json.loads((root / "src/assets/MathJax/resources.json").read_text())
    office = manifest["profiles"]["office"]
    desktop = manifest["profiles"]["desktop"]
    assert "output/chtml.js" in desktop and "output/chtml.js" not in office
    assert not any("/chtml" in path or path.endswith(".woff") for path in office)
    assert {
        "startup.js",
        "runtime.js",
        "config.js",
        "office.js",
        "output/svg.js",
        "fonts/mathjax-mhchem-font-extension/svg.js",
    } <= set(office)


def test_preview_and_export_have_separate_scale_settings():
    preview = loader_script(scale=1.2)
    export = loader_script(output="svg", typeset=False)
    assert '"scale": 1.2' in preview
    assert '"scale": 1,' in export
    assert ASSET_ROOT.resolve().as_uri() in export
